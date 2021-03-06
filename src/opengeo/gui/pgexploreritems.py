import os
from PyQt4 import QtGui, QtCore
from qgis.core import *
from opengeo.postgis.connection import PgConnection
from opengeo.gui.exploreritems import TreeItem
from dialogs.layerdialog import PublishLayerDialog
from dialogs.userpasswd import UserPasswdDialog
from dialogs.importvector import ImportIntoPostGISDialog
from dialogs.pgconnectiondialog import NewPgConnectionDialog
from dialogs.createtable import DlgCreateTable
from opengeo.gui.qgsexploreritems import QgsLayerItem

pgIcon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/postgis.png")   
 
class PgTreeItem(TreeItem):
    
    def iconPath(self):
        return os.path.dirname(__file__) + "/../images/postgis.png"
        
class PgConnectionsItem(PgTreeItem):

    def __init__(self):             
        TreeItem.__init__(self, None, pgIcon, "PostGIS connections")
        self.databases = [] 
        
    def populate(self):
        self.databases = []         
        settings = QtCore.QSettings()
        settings.beginGroup(u'/PostgreSQL/connections')
        for name in settings.childGroups():
            settings.beginGroup(name)
            try:                                            
                conn = PgConnection(name, settings.value('host'), int(settings.value('port')), 
                                settings.value('database'), settings.value('username'), 
                                settings.value('password'))                 
                item = PgConnectionItem(conn)
                if conn.isValid:                              
                    item.populate()
                    self.databases.append(conn)                    
                else:    
                    #if there is a problem connecting, we add the unpopulated item with the error icon
                    #TODO: report on the problem
                    wrongConnectionIcon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/wrong.gif")                 
                    item.setIcon(0, wrongConnectionIcon)                    
                self.addChild(item)
            except Exception, e:                
                pass
            finally:                            
                settings.endGroup()  
        
    def contextMenuActions(self, tree, explorer):       
        icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/add.png")  
        newConnectionAction = QtGui.QAction(icon, "New connection...", explorer)
        newConnectionAction.triggered.connect(lambda: self.newConnection(explorer))                                             
        return [newConnectionAction]
                 
    def newConnection(self, explorer):
        dlg = NewPgConnectionDialog(explorer)
        dlg.exec_()
        if dlg.conn is not None:
            self.databases.append(dlg.conn)
            item = PgConnectionItem(dlg.conn)
            if dlg.conn.isValid:                              
                item.populate()                
            else:                    
                wrongConnectionIcon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/wrong.gif")                 
                item.setIcon(0, wrongConnectionIcon)                
            self.addChild(item)
            
                  
class PgConnectionItem(PgTreeItem): 
    
    def __init__(self, conn):                      
        TreeItem.__init__(self, conn, pgIcon)
        self.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsDropEnabled)          
        
    def refreshContent(self, explorer):
        self.takeChildren()              
        self.populate()   
                
    def populate(self):
        if not self.element.isValid:
            dlg = UserPasswdDialog()
            dlg.exec_()
            if dlg.user is None:
                return
            self.element.reconnect(dlg.user, dlg.passwd)            
            if not self.element.isValid:
                QtGui.QMessageBox.warning(None, "Error connecting to DB", "Cannot connect to the database")
                return 
            if self.element not in self.parent().databases:
                self.parent().databases.append(self.element)
            self.setIcon(0, pgIcon)
        schemas = self.element.schemas()
        for schema in schemas:
            schemItem = PgSchemaItem(schema)
            schemItem.populate()
            self.addChild(schemItem)
            
    def contextMenuActions(self, tree, explorer): 
        icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/edit.png")
        editAction = QtGui.QAction(icon, "Edit...", explorer)
        editAction.triggered.connect(lambda: self.editConnection(explorer))
        icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/delete.gif")
        deleteAction = QtGui.QAction(icon, "Remove...", explorer)
        deleteAction.triggered.connect(lambda: self.deleteConnection(explorer))
        actions = [editAction, deleteAction]
        if self.element.isValid:            
            icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/add.png")
            newSchemaAction = QtGui.QAction(icon, "New schema...", explorer)
            newSchemaAction.triggered.connect(lambda: self.newSchema(explorer))
            icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/sql_window.png")  
            sqlAction = QtGui.QAction(icon, "Run SQL...", explorer)
            sqlAction.triggered.connect(self.runSql)     
            icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/postgis_import.png") 
            importAction = QtGui.QAction(icon, "Import files...", explorer)
            importAction.setEnabled(self.childCount() != 0)
            importAction.triggered.connect(lambda: self.importIntoDatabase(explorer))                                        
            actions.extend([newSchemaAction, sqlAction, importAction])        
        return actions
        
    def _getDescriptionHtml(self, tree, explorer):  
        if not self.element.isValid:            
            html = ('<p>Cannot connect to this database. This might be caused by missing user/passwd credentials.'
                    'Try <a href="refresh">refreshing</a> the connection, to enter new credentials and retry to connect</p>')     
            return html
        else:
            return TreeItem._getDescriptionHtml(self, tree, explorer)

    def linkClicked(self, tree, explorer, url):
        if not self.element.isValid:
            self.refreshContent(explorer)
        else:
            TreeItem.linkClicked(self, tree, explorer, url)        
             
    def acceptDroppedUris(self, tree, explorer, uris):
        if not self.element.isValid:
            return
        if uris:
            files = []
            for uri in uris:
                if isinstance(uri, basestring):
                    files.append(uri)
                else:                                       
                    files.append(uri.uri)                  
            dlg = ImportIntoPostGISDialog(explorer.pgDatabases(), self.element, toImport = files)
            dlg.exec_()
            if dlg.ok:           
                explorer.setProgressMaximum(len(dlg.toImport), "Import layers into PostGIS")
                for i, filename in enumerate(dlg.toImport):
                    explorer.setProgress(i)
                    explorer.run(self.element.importFileOrLayer,
                                None, 
                                [],
                                filename, dlg.schema, dlg.tablename, not dlg.add)
                explorer.resetActivity()        
                return [self]
            return []
        else:
            return []
        
    def acceptDroppedItems(self, tree, explorer, items):
        if not self.element.isValid:
            return
        toUpdate = set()
        toImport = []
        for item in items:         
            if isinstance(item, QgsLayerItem):
                if item.element.type() == QgsMapLayer.VectorLayer:
                    toImport.append(item.element)        
        if toImport:
            dlg = ImportIntoPostGISDialog(explorer.pgDatabases(), self.element, toImport = toImport)
            dlg.exec_()
            if dlg.ok: 
                if len(dlg.toImport) > 1:
                    explorer.setProgressMaximum(len(dlg.toImport), "Import layers into PostGIS")           
                for i, layer in enumerate(dlg.toImport):  
                    explorer.setProgress(i)                  
                    if not explorer.run(self.element.importFileOrLayer, 
                                        None, 
                                        [],
                                        layer, dlg.schema, dlg.tablename, not dlg.add):
                        break
                explorer.resetActivity()
                toUpdate.add(self)
        
        return toUpdate          
        
    def deleteConnection(self, explorer):
        settings = QtCore.QSettings()
        settings.beginGroup("/PostgreSQL/connections/" + self.element.name) 
        settings.remove(""); 
        settings.endGroup();
        self.parent().refreshContent(explorer)
        explorer.setToolbarActions([])
        
    def importIntoDatabase(self, explorer):           
        dlg = ImportIntoPostGISDialog(explorer.pgDatabases(), self.element)
        dlg.exec_()
        if dlg.ok:  
            explorer.setProgressMaximum(len(dlg.toImport), "Import layers into PostGIS")          
            for i, filename in enumerate(dlg.toImport):
                explorer.setProgress(i)
                explorer.run(self.element.importFileOrLayer, 
                            None, 
                            [],
                            filename, dlg.schema, dlg.tablename, not dlg.add)
            explorer.resetActivity()
        self.refreshContent(explorer)
          
    def runSql(self):
        pass
    
    def newSchema(self, explorer):            
        text, ok = QtGui.QInputDialog.getText(explorer, "Schema name", "Enter name for new schema", text="schema")
        if ok:
            explorer.run(self.element.geodb.create_schema, 
                        "Create schema '" + text + "'",
                         [self], 
                         text) 
            
    def editConnection(self, explorer):
        dlg = NewPgConnectionDialog(explorer, self.element)
        dlg.exec_()
        if dlg.conn is not None:
            self.parent().refreshContent(explorer) 
        
                    
class PgSchemaItem(PgTreeItem): 
    
    def __init__(self, schema): 
        pgIcon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/namespace.png")                        
        TreeItem.__init__(self, schema, pgIcon)
        self.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsDropEnabled)
        
    def populate(self):
        tables = self.element.tables()
        for table in tables:
            tableItem = PgTableItem(table)            
            self.addChild(tableItem)      

    def contextMenuActions(self, tree, explorer):                        
        newTableIcon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/new_table.png")                         
        newTableAction = QtGui.QAction(newTableIcon, "New table...", explorer)
        newTableAction.triggered.connect(lambda: self.newTable(explorer))
        icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/delete.gif")                                                                    
        deleteAction= QtGui.QAction(icon, "Delete", explorer)
        deleteAction.triggered.connect(lambda: self.deleteSchema(explorer)) 
        icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/rename.png") 
        renameAction= QtGui.QAction(icon, "Rename...", explorer)
        renameAction.triggered.connect(lambda: self.renameSchema(explorer))
        icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/postgis_import.png")
        importAction = QtGui.QAction(icon, "Import files...", explorer)
        importAction.triggered.connect(lambda: self.importIntoSchema(explorer))                            
        return [newTableAction, deleteAction, renameAction, importAction]

    def importIntoSchema(self, explorer):
        dlg = ImportIntoPostGISDialog(explorer.pgDatabases(), self.element.conn, self.element)
        dlg.exec_()
        if dlg.ok:        
            explorer.setProgressMaximum(len(dlg.toImport), "Import layers into PostGIS")    
            for i, filename in enumerate(dlg.toImport):
                explorer.setProgress(i)
                explorer.run(self.element.conn.importFileOrLayer, 
                            None, 
                            [],
                            filename, dlg.schema, dlg.tablename, not dlg.add)
            explorer.resetActivity()
        self.refreshContent(explorer)
        
    def deleteSchema(self, explorer):
        explorer.run(self.element.conn.geodb.delete_schema, 
                          "Delete schema '" + self.element.name + "'",
                          [self.parent()], 
                          self.element.name)
    
    def renameSchema(self, explorer):
        text, ok = QtGui.QInputDialog.getText(explorer, "Schema name", "Enter new name for schema", text="schema")
        if ok:
            explorer.run(self.element.conn.geodb.rename_schema, 
                          "Rename schema '" + self.element.name + "'  to '" + text + "'", 
                          [self.parent()], 
                          self.element.name, text)      
    
    def newTable(self, explorer):
        dlg = DlgCreateTable(self.element)  
        dlg.exec_()  
        if dlg.ok:
            def _create():
                db = self.element.conn.geodb
                db.create_table(dlg.name, dlg.fields, dlg.pk)
                if dlg.useGeomColumn:
                    db.add_geometry_column(dlg.name, dlg.geomType, self.element.name, dlg.geomColumn, 
                                                             dlg.geomSrid, dlg.geomDim)
                    if dlg.useSpatialIndex:
                        db.create_spatial_index(dlg.name, self.element.name, dlg.geomColumn)
            explorer.run(_create, "Create PostGIS table", [self])
    
    def acceptDroppedUris(self, tree, explorer, uris):
        if uris:
            files = []
            for uri in uris:                            
                if isinstance(uri, basestring):
                    files.append(uri)
                else:                                       
                    files.append(uri.uri)         
            dlg = ImportIntoPostGISDialog(explorer.pgDatabases(), self.element.conn, schema = self.element, toImport = files)
            dlg.exec_()
            if dlg.ok:
                if len(dlg.toImport) > 1:
                    explorer.setProgressMaximum(len(dlg.toImport), "Import layers into PostGIS")           
                for i, filename in enumerate(dlg.toImport):
                    explorer.setProgress(i)
                    if not explorer.run(self.element.conn.importFileOrLayer, 
                                        None, 
                                        [],
                                        filename, dlg.schema, dlg.tablename, not dlg.add):
                        break
                explorer.resetActivity()                       
                return [self]
            return []
        else:
            return []    
        
    def acceptDroppedItems(self, tree, explorer, items):
        toUpdate = set()
        toImport = []
        for item in items:                   
            if isinstance(item, QgsLayerItem):
                if item.element.type() == QgsMapLayer.VectorLayer:
                    toImport.append(item.element)
        if toImport:
            dlg = ImportIntoPostGISDialog(explorer.pgDatabases(), self.element.conn, schema = self.element, toImport = toImport)
            dlg.exec_()
            if dlg.ok:
                if len(dlg.toImport) > 1:
                    explorer.setProgressMaximum(len(dlg.toImport), "Import layers into PostGIS")           
                for i, layer in enumerate(dlg.toImport):  
                    explorer.setProgress(i)                  
                    if not explorer.run(self.element.conn.importFileOrLayer, 
                                        None, 
                                        [],
                                        layer, dlg.schema, dlg.tablename, not dlg.add):
                        break                                            
                explorer.resetActivity()
                toUpdate.add(self)
        
        return toUpdate                  
        
class PgTableItem(PgTreeItem): 
    def __init__(self, table):                               
        TreeItem.__init__(self, table, self.getIcon(table))
        self.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsDragEnabled)
        
    def getIcon(self, table):        
        tableIcon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/table.png")
        viewIcon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/view.png")
        layerPointIcon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/layer_point.png")
        layerLineIcon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/layer_line.png")
        layerPolygonIcon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/layer_polygon.png")        
        layerUnknownIcon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/layer_unknown.png")
            
        if table.geomtype is not None:        
            if table.geomtype.find('POINT') != -1:
                return layerPointIcon
            elif table.geomtype.find('LINESTRING') != -1:
                return layerLineIcon
            elif table.geomtype.find('POLYGON') != -1:
                return layerPolygonIcon
            return layerUnknownIcon        

        if table.isView:
            return viewIcon
        
        return tableIcon
    
    def contextMenuActions(self, tree, explorer):        
        icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/publish-to-geoserver.png") 
        publishPgTableAction = QtGui.QAction(icon, "Publish...", explorer)
        publishPgTableAction.triggered.connect(lambda: self.publishPgTable(tree, explorer))            
        publishPgTableAction.setEnabled(len(explorer.catalogs()) > 0) 
        icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/delete.gif")     
        deleteAction= QtGui.QAction(icon, "Delete", explorer)
        deleteAction.triggered.connect(lambda: self.deleteTable(explorer))  
        icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/rename.png") 
        renameAction= QtGui.QAction(icon, "Rename...", explorer)
        renameAction.triggered.connect(lambda: self.renameTable(explorer))                 
        vacuumAction= QtGui.QAction("Vacuum analyze", explorer)
        vacuumAction.triggered.connect(lambda: self.vacuumTable(explorer))
        return [publishPgTableAction, deleteAction, renameAction, vacuumAction]
           
    def multipleSelectionContextMenuActions(self, tree, explorer, selected):   
        icon = QtGui.QIcon(os.path.dirname(__file__) + "/../images/delete.gif")     
        deleteAction= QtGui.QAction(icon, "Delete", explorer)
        deleteAction.triggered.connect(lambda: self.deleteTables(explorer, selected))   
        return [deleteAction]
    
    def acceptDroppedItems(self, tree, explorer, items):        
        toImport = []
        for item in items:                   
            if isinstance(item, QgsLayerItem):
                if item.element.type() == QgsMapLayer.VectorLayer:
                    toImport.append(item.element)
        if toImport:
            if len(toImport) > 1:
                explorer.setProgressMaximum(len(toImport), "Import layers into PostGIS table")    
            for i, layer in enumerate(toImport):
                explorer.setProgress(i)
                if not explorer.run(self.element.conn.importFileOrLayer, 
                            "Import into PostGIS table", 
                            [],
                            layer, self.element.schema, self.element.name, False):
                    break
                
            explorer.resetActivity()
        
        return []
    
    def acceptDroppedUris(self, tree, explorer, uris):
        if uris:
            files = []
            for uri in uris:                            
                if isinstance(uri, basestring):
                    files.append(uri)
                else:                                       
                    files.append(uri.uri)         
            if len(files) > 1:
                explorer.setProgressMaximum(len(files), "Import layers into PostGIS table")           
            for i, filename in enumerate(files):
                explorer.setProgress(i)
                if not explorer.run(self.element.conn.importFileOrLayer, 
                                   "Import into PostGIS table", 
                                    [],
                                    filename, self.element.schema, self.element.name, False):
                    break     
            explorer.resetActivity()                       
        return []    
        
               
    def vacuumTable(self, explorer):
        explorer.run(self.element.conn.geodb.vacuum_analyze, 
                  "Vacuum table " + self.element.name,
                  [self.parent()], 
                  self.element.name, self.element.schema)
    
    def deleteTable(self, explorer):
        self.deleteTables(explorer, [self])
        
    def deleteTables(self, explorer, items):
        explorer.setProgressMaximum(len(items), "Delete tables")
        for i, item in enumerate(items):                      
            explorer.run(item.element.conn.geodb.delete_table, 
                          None, 
                          [item.parent()], 
                          item.element.name, item.element.schema)
            explorer.setProgress(i+1)
        explorer.resetActivity()
    
    def renameTable(self, explorer):
        text, ok = QtGui.QInputDialog.getText(explorer, "Table name", "Enter new name for table", text="table")
        if ok:
            explorer.run(self.element.conn.geodb.rename_table, 
                          "Rename table '" + self.element.name + "' to '" + text + "'",
                          [self.parent()], 
                          self.element.name, text, self.element.schema)      
    
    
    def publishPgTable(self, tree, explorer):
        dlg = PublishLayerDialog(explorer.catalogs())
        dlg.exec_()      
        if dlg.catalog is None:
            return
        cat = dlg.catalog          
        catItem = tree.findAllItems(cat)[0]
        toUpdate = [catItem]                    
        explorer.run(self._publishTable,
                 "Publish table '" + self.element.name + "'",
                 toUpdate,
                 self.element, cat, dlg.workspace)
        
                
    def _publishTable(self, table, catalog = None, workspace = None):
        if catalog is None:
            pass       
        workspace = workspace if workspace is not None else catalog.get_default_workspace()        
        connection = table.conn 
        geodb = connection.geodb      
        catalog.create_pg_featurestore(connection.name,                                           
                                       workspace = workspace,
                                       overwrite = True,
                                       host = geodb.host,
                                       database = geodb.dbname,
                                       schema = table.schema,
                                       port = geodb.port,
                                       user = geodb.user,
                                       passwd = geodb.passwd)
        catalog.create_pg_featuretype(table.name, connection.name, workspace, "EPSG:" + str(table.srid))  


    def populate(self):
        pass
