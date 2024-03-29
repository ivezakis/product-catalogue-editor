import io
import re
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from PyQt6.QtCore import QRunnable, pyqtSlot, QThreadPool, QObject, pyqtSignal
from PyQt6.QtGui import QUndoStack
from PyQt6.QtWidgets import QMainWindow, QMenu, QMessageBox, QFileDialog

import undoCommands
from views import main_window_ui as mwui
from table.model import TableModel, TableModel2
from views.find_and_replace import FindReplaceWidget
from views.rename_header import RenameHeaderDialog

from PIL import Image
import shortuuid
import automations.search_for_image as sfi
import automations.image_processing as imp


class Window(QMainWindow, mwui.Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.threadpool = QThreadPool()
        self.find_rep_widg = FindReplaceWidget(self)
        self.rename_header_dialog = RenameHeaderDialog(self)
        self.setupUi(self)
        self.undo_stack = QUndoStack(self)
        self.connect_signals_slots()
        self.dockWidget.close()
        self.dockWidget_2.close()
        self.fp = None

    def connect_signals_slots(self):
        self.actionExit.triggered.connect(self.close)
        self.actionAbout.triggered.connect(self.about)
        self.actionOpen.triggered.connect(self.load_file)
        self.actionInsert_Row_Above.triggered.connect(self.insert_row_above)
        self.actionInsert_Row_Below.triggered.connect(self.insert_row_below)
        self.actionInsert_Column_Left.triggered.connect(self.insert_column_left)
        self.actionInsert_Column_Right.triggered.connect(
            self.insert_column_right)
        self.actionDelete_Row.triggered.connect(self.delete_row)
        self.actionDelete_Column.triggered.connect(self.delete_column)
        self.actionUndo.triggered.connect(self.undo_stack.undo)
        self.actionRedo.triggered.connect(self.undo_stack.redo)
        self.undo_stack.canUndoChanged.connect(self.update_undo_redo)
        self.undo_stack.canRedoChanged.connect(self.update_undo_redo)
        self.actionSave_as.triggered.connect(self.save_file_as)
        self.actionSave.triggered.connect(self.save_file)
        self.actionCSV.triggered.connect(self.export_csv)
        self.actionExcel.triggered.connect(self.export_xls)
        self.actionJSON.triggered.connect(self.export_json)
        self.actionHDF5.triggered.connect(self.export_hdf)
        self.actionMarkdown.triggered.connect(self.export_md)
        self.actionHTML.triggered.connect(self.export_html)
        self.actionLaTeX.triggered.connect(self.export_latex)
        self.actionPickle.triggered.connect(self.export_pickle)
        self.actionFind_and_Replace.triggered.connect(self.find_and_replace)
        self.actionStandardise_Data.triggered.connect(self.standardise_data)
        self.actionMachine_Learning_Toolbox.triggered.connect(self.toggle_dock)
        self.actionUnique_Words_by_Column.triggered.connect(self.toggle_dock_2)
        self.refreshUniqueWordResultsBtn.clicked.connect(
            self.refresh_unique_words)
        self.actionRename_Header.triggered.connect(self.rename_header)
        self.find_imgs_btn.clicked.connect(self.add_img_urls)

    def tableContextMenuEvent(self, pos):
        context = QMenu(self)
        context.addAction(self.actionInsert_Row_Above)
        context.addAction(self.actionInsert_Row_Below)
        context.addSeparator()
        context.addAction(self.actionInsert_Column_Left)
        context.addAction(self.actionInsert_Column_Right)
        context.addSeparator()
        context.addAction(self.actionRename_Header)
        context.addSeparator()
        context.addAction(self.actionDelete_Row)
        context.addAction(self.actionDelete_Column)
        context.exec(self.tableView.viewport().mapToGlobal(pos))

    def about(self):
        QMessageBox.about(
            self,
            "Simple CSV Editor",
            "<p>v1.0.0</p>"
        )

    def load_file(self):
        try:
            self.fp = Path(QFileDialog.getOpenFileName(
                self, 'Open file', '',
                "Spreadsheet Files (*.csv *.xls *.xlsx)")[0])
            extension = self.fp.suffix
            if extension == '.csv':
                df = pd.read_csv(self.fp)
            elif extension == '.xls' or extension == '.xlsx':
                df = pd.read_excel(self.fp, engine='openpyxl')

            if df.size == 0:
                return 0

            df = df.convert_dtypes()
            self.model = TableModel(df, self)
            self.tableView.setModel(self.model)

            self.unique_words_model = TableModel2(pd.DataFrame(), self,
                                                  self.model)
            self.unique_words_model.header = np.array(['Unique Words'])
            self.uniqueWordsTable.setModel(self.unique_words_model)

            self.tableView.customContextMenuRequested.connect(
                self.tableContextMenuEvent)
            self.undo_stack.setClean()
            self.actionSave.setEnabled(True)
            self.actionSave_as.setEnabled(True)
            self.actionInsert_Row_Below.setEnabled(True)
            self.actionInsert_Row_Above.setEnabled(True)
            self.actionInsert_Column_Right.setEnabled(True)
            self.actionInsert_Column_Left.setEnabled(True)
            self.actionDelete_Row.setEnabled(True)
            self.actionDelete_Column.setEnabled(True)
            self.menuExport_As.setEnabled(True)
            self.actionFind_and_Replace.setEnabled(True)
            self.actionStandardise_Data.setEnabled(True)
            self.actionRename_Header.setEnabled(True)
            self.refreshUniqueWordResultsBtn.setEnabled(True)
            self.find_imgs_btn.setEnabled(True)
            self.update_column_combos()

        except Exception as e:
            raise e

    def save_file(self):
        try:
            self.save(self.fp)
        except Exception as e:
            print(e)

    def save_file_as(self):
        try:
            fp = Path(
                QFileDialog.getSaveFileName(
                    self, 'Save file', str(self.fp),
                    'All files (*%s)'.format(self.fp.suffix))[0])
            self.save(fp)
        except Exception as e:
            print(e)

    def export_csv(self):
        self.export('.csv')

    def export_xls(self):
        self.export('.xls')

    def export_json(self):
        self.export('.json')

    def export_hdf(self):
        self.export('.hdf5')

    def export_html(self):
        self.export('.html')

    def export_md(self):
        self.export('.md')

    def export_latex(self):
        self.export('.tex')

    def export_pickle(self):
        self.export('.pickle')

    def export(self, ft):
        fp = Path(QFileDialog.getSaveFileName(self, 'Save file',
                                              str(self.fp.with_suffix(ft)),
                                              'All files (*%s)'.format(ft))[0])
        self.save(fp)

    def save(self, fp):
        ft = fp.suffix
        df = pd.DataFrame(self.model._items, columns=self.model.header)
        if ft == '.csv':
            df.to_csv(fp, index=False)
        elif ft == '.xls':
            df.to_excel(fp, index=False)
        elif ft == '.json':
            df.to_json(fp, index=False)
        elif ft == '.hdf5':
            df.to_hdf(fp, index=False)
        elif ft == '.html':
            df.to_html(fp, index=False)
        elif ft == '.md':
            df.to_markdown(fp, index=False)
        elif ft == '.tex':
            df.to_latex(fp, index=False)
        elif ft == '.pickle':
            df.to_pickle(fp, index=False)

    def insert_row_above(self):
        indexes = self.tableView.selectedIndexes()
        if indexes:
            command = undoCommands.CommandInsertRow(
                self.model,
                indexes[0].row(), None,
                "Insert a row above the current selection")
            self.undo_stack.push(command)

    def insert_row_below(self):
        indexes = self.tableView.selectedIndexes()
        if indexes:
            command = undoCommands.CommandInsertRow(
                self.model,
                indexes[0].row() + 1, None,
                "Insert a row below the current selection")
            self.undo_stack.push(command)

    def insert_column_left(self):
        indexes = self.tableView.selectedIndexes()
        if indexes:
            command = undoCommands.CommandInsertCol(
                self.model,
                indexes[0].column(), None,
                "Insert a column to the left of the current selection")
            self.undo_stack.push(command)

    def insert_column_right(self):
        indexes = self.tableView.selectedIndexes()
        if indexes:
            command = undoCommands.CommandInsertCol(
                self.model,
                indexes[0].column() + 1,
                None,
                "Insert a column to the right of the current selection")
            self.undo_stack.push(command)

    def delete_row(self):
        indexes = self.tableView.selectedIndexes()
        if indexes:
            command = undoCommands.CommandDeleteRow(
                self.model,
                indexes[0].row(),
                "Delete currently selected row")
            self.undo_stack.push(command)

    def delete_column(self):
        indexes = self.tableView.selectedIndexes()
        if indexes:
            command = undoCommands.CommandDeleteCol(
                self.model,
                indexes[0].column(),
                "Delete currently selected column")
            self.undo_stack.push(command)

    def update_undo_redo(self):
        self.actionUndo.setEnabled(self.undo_stack.canUndo())
        self.actionRedo.setEnabled(self.undo_stack.canRedo())

    def find_and_replace(self):
        self.find_rep_widg.show()

    def standardise_data(self):
        command = undoCommands.CommandStandardize(
            self.model,
            "Standardise data"
        )
        self.undo_stack.push(command)

    def toggle_dock(self):
        if self.actionMachine_Learning_Toolbox.isChecked():
            self.dockWidget.show()
        else:
            self.dockWidget.close()

    def toggle_dock_2(self):
        if self.actionUnique_Words_by_Column.isChecked():
            self.dockWidget_2.show()
        else:
            self.dockWidget_2.close()

    def rename_header(self):
        indexes = self.tableView.selectedIndexes()
        if indexes:
            self.rename_header_dialog = RenameHeaderDialog(indexes[0], self)
            self.rename_header_dialog.show()

    def refresh_unique_words(self):
        values = self.model.items[
                 :, self.categoryComboUniqueWords.currentIndex()]

        vmatch = np.vectorize(
            lambda x: bool(re.search(
                r'[ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρστυφχψωςΆΈΊΪΌΎΫΏάέήϊΐόύϋΰώ]|^(?![\s\S])',
                x)))

        if self.findGreekCheck.isChecked():
            bool_table = vmatch(values)
            self.unique_words_model.items = np.unique(
                values[bool_table]).reshape((-1, 1))
        else:
            self.unique_words_model.items = np.unique(values).reshape((-1, 1))

    def update_column_combos(self):
        self.imgs_combo.clear()
        self.imgs_combo.addItems(self.model.header)

        self.description_combo.clear()
        self.description_combo.addItems(self.model.header)

        self.category_combo.clear()
        self.category_combo.addItems(self.model.header)

        self.sku_combo.clear()
        self.sku_combo.addItems(self.model.header)

        self.features_combo.clear()
        self.features_combo.addItems(self.model.header)

        self.categoryComboUniqueWords.clear()
        self.categoryComboUniqueWords.addItems(self.model.header)

    def add_img_urls(self):
        worker = AddImgUrlsWorker(self)
        worker.signals.result.connect(self.worker_result)
        worker.signals.start.connect(self.worker_start)
        worker.signals.end.connect(self.worker_end)
        worker.signals.progress.connect(self.update_progress)
        worker.signals.error.connect(self.worker_error)

        self.threadpool.start(worker)

    def worker_result(self, result):
        idx = self.model.createIndex(
            result["row"], result["col"])
        img_name = shortuuid.uuid() + '.jpeg'

        img = result["img"]
        if img:
            img.save(Path(self.fp).parent.joinpath(img_name), 'jpeg')
            self.model.edit_item(idx, img_name)
        else:
            self.model.edit_item(idx, '')

    def worker_start(self):
        self.find_imgs_btn.setEnabled(False)

    def worker_end(self):
        self.find_imgs_btn.setEnabled(True)

    def worker_error(self, t):
        print("ERROR: %s" % t)

    def update_progress(self, progress):
        self.progressBar.setValue(progress)


class AddImgUrlsWorker(QRunnable):
    def __init__(self, parent):
        super().__init__()
        self.job_id = uuid.uuid4().hex
        self.signals = AddImgUrlsWorkerSignals()
        self.items = np.copy(parent.model.items)
        self.imgs_combo_idx = parent.imgs_combo.currentIndex()
        self.desc_combo_idx = parent.description_combo.currentIndex()

    @pyqtSlot()
    def run(self):
        try:
            self.signals.start.emit()
            total_n = self.items.shape[0]
            for i, item in enumerate(self.items):
                progress_pc = int(100 * float(i + 1) / total_n)
                img_url = sfi.search(
                    re.sub(r'\([^)]*\)', '', item[self.desc_combo_idx]))
                img_url = re.split("\?", img_url)[0]
                self.signals.progress.emit(progress_pc)

                try:
                    response = requests.get(img_url, stream=True)

                    img = Image.open(response.raw)
                    img = imp.resize(
                        Image.fromarray(imp.crop_image(np.array(img), 250)),
                        500, 500)

                    self.signals.result.emit(
                        {
                            "img_url": img_url,
                            "row": i,
                            "col": self.imgs_combo_idx,
                            "img": img
                        }
                    )
                except Exception:
                    self.signals.result.emit(
                        {
                            "img_url": img_url,
                            "row": i,
                            "col": self.imgs_combo_idx,
                            "img": None
                        }
                    )
            self.signals.end.emit()
        except Exception as e:
            self.signals.error.emit(str(e))


class AddImgUrlsWorkerSignals(QObject):
    start = pyqtSignal()
    end = pyqtSignal()
    result = pyqtSignal(dict)
    progress = pyqtSignal(int)
    error = pyqtSignal(str)
