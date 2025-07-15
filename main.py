import os
import shutil
import io
import sys
import tempfile
from typing import List, Dict, Any, Optional

# NEU: appdirs für plattformübergreifende Pfade zu Benutzerdaten
from appdirs import user_data_dir

# --- GUI-Bibliotheken ---
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QFrame, QGroupBox,
    QFileDialog, QMessageBox, QStackedWidget, QInputDialog, QLineEdit 
)
from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal, QSize, Slot, QUrl, QEvent, QPointF, QRectF 
# QIcon bleibt importiert
from PySide6.QtGui import QPixmap, QFontDatabase, QDragEnterEvent, QDropEvent, QPalette, QColor, QMouseEvent, QPainter, QPen, QWheelEvent, QImage, QIcon 


# qtawesome für moderne Icons importieren
import qtawesome as qta

from PySide6.QtWidgets import QStyleFactory

# --- Bildverarbeitung & PDF ---
from PIL import Image
from PIL.ImageQt import ImageQt
import numpy as np
import cv2

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        print("FEHLER: PyMuPDF nicht gefunden.")
        sys.exit(1)


# --- Globale Konfiguration & Pfade ---
def get_base_path() -> str:
    """
    Ermittelt den Basispfad für den Zugriff auf Ressourcendateien.
    Funktioniert sowohl im Entwicklungsmodus als auch in einer
    mit PyInstaller gebündelten Anwendung.
    """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return base_path


BASE_PATH = get_base_path()

# Pfad für benutzerdefinierte Templates (immer beschreibbar)
APP_NAME = "DarkMark"
APP_AUTHOR = "JohannesGschwendtner" 
USER_TEMPLATES_PATH = os.path.join(user_data_dir(APP_NAME, APP_AUTHOR), "darkmark_user_templates")

MATCH_THRESHOLD = 0.6 
RENDER_DPI = 300


# ==============================================================================
#      KERNAUFGABEN (load_template_images angepasst)
# ==============================================================================

# load_template_images lädt jetzt NUR noch aus user_template_dir
def load_template_images(user_template_dir: str) -> List[Dict[str, Any]]:
    templates_data = []
    
    # Sicherstellen, dass der Benutzer-Template-Ordner existiert
    if not os.path.exists(user_template_dir):
        try:
            os.makedirs(user_template_dir)
            print(f"DEBUG: Benutzer-Template-Ordner erstellt: {user_template_dir}")
        except OSError as e:
            print(f"WARNUNG: Konnte Benutzer-Template-Ordner nicht erstellen: {user_template_dir}: {e}")
            return [] 
            
    if os.path.isdir(user_template_dir):
        for filename in os.listdir(user_template_dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff')):
                file_path = os.path.join(user_template_dir, filename)
                try:
                    template_img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
                    if template_img is None: 
                        print(f"WARNUNG: Konnte Benutzer-Bild {filename} nicht als Template laden (cv2.imread gab None zurück).")
                        continue
                    templates_data.append({
                        "name": filename, "cv_image": template_img,
                        "width": template_img.shape[1], "height": template_img.shape[0],
                        "source": "user" 
                    })
                except Exception as e:
                    print(f"DEBUG: Fehler beim Laden von Benutzer-Template {file_path}: {e}")
    else:
        print(f"DEBUG: Benutzer-Template-Ordner nicht gefunden: {user_template_dir}")

    print(f"DEBUG: Loaded {len(templates_data)} total templates from user directory: {user_template_dir}.")
    return templates_data


def page_to_pixmap(doc: fitz.Document, page_num: int, target_size: QSize) -> QPixmap | None:
    try:
        page = doc.load_page(page_num)
        mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        q_img = ImageQt(img)
        pixmap = QPixmap.fromImage(q_img)
        return pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    except Exception as e:
        print(f"Fehler beim Rendern von Seite {page_num}: {e}")
        return None


# find_and_redact_on_page (Originalversion)
def find_and_redact_on_page(page: fitz.Page, templates_data_list: list, threshold: float) -> int:
    redacted_count = 0
    mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    page_cv_img_gray = cv2.imdecode(np.frombuffer(pix.tobytes("png"), np.uint8), cv2.IMREAD_GRAYSCALE)
    if page_cv_img_gray is None: 
        print(f"WARNUNG: Konnte Seite {page.number+1} nicht in Graustufenbild konvertieren.")
        return 0
    inv_mat = ~mat
    for template in templates_data_list:
        template_cv = template["cv_image"]
        if template_cv is None or template_cv.size == 0:
            print(f"WARNUNG: Leeres oder ungültiges Template übersprungen: {template['name']}")
            continue
        
        if template_cv.shape[0] > page_cv_img_gray.shape[0] or template_cv.shape[1] > page_cv_img_gray.shape[1]:
            print(f"WARNUNG: Template {template['name']} ist größer als die Seite, übersprungen.")
            continue

        try:
            res = cv2.matchTemplate(page_cv_img_gray, template_cv, cv2.TM_CCOEFF_NORMED)
            locs = np.where(res >= threshold)
        except cv2.error as e:
            print(f"ERROR: cv2.matchTemplate failed for template {template['name']} on page {page.number+1}: {e}")
            continue 

        for pt in zip(*locs[::-1]):
            rect = fitz.Rect(pt[0], pt[1], pt[0] + template_cv.shape[1], pt[1] + template_cv.shape[0]) * inv_mat
            
            page.add_redact_annot(rect, fill=(0, 0, 0))
            redacted_count += 1
            print(f"DEBUG: Found '{template['name']}' at {rect} on page {page.number+1}.")

    if redacted_count > 0:
        page.apply_redactions()
        print(f"DEBUG: Page {page.number + 1}: Applied {redacted_count} redactions.")
    else:
        print(f"DEBUG: Page {page.number + 1}: No redactions applied.")
    return redacted_count


# ==============================================================================
#      THREADING-MODELLE MIT QThreadPool (Unverändert)
# ==============================================================================

class WorkerSignals(QObject):
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(str)

class RedactionTask(QRunnable): 
    def __init__(self, input_path: str, output_path: str, templates: list):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.templates = templates
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            total_redactions = 0
            print(f"DEBUG: RedactionTask: Processing {os.path.basename(self.input_path)}...")
            with fitz.open(self.input_path) as doc:
                for page in doc:
                    total_redactions += find_and_redact_on_page(page, self.templates, MATCH_THRESHOLD)

                if total_redactions > 0:
                    doc.save(self.output_path, garbage=4, deflate=True)
                    print(f"DEBUG: RedactionTask: Saved {os.path.basename(self.output_path)} with {total_redactions} redactions.")
                else:
                    print(f"DEBUG: RedactionTask: No redactions found for {os.path.basename(self.input_path)}, not saving.")

            self.signals.finished.emit({
                "input_path": self.input_path,
                "output_path": self.output_path,
                "redactions": total_redactions
            })
        except Exception as e:
            print(f"ERROR: RedactionTask failed for {os.path.basename(self.input_path)}: {e}")
            self.signals.error.emit(f"Fehler bei Vorschau '{os.path.basename(self.input_path)}': {e}")

class PreviewRedactionTask(QRunnable): 
    def __init__(self, original_pdf_path: str, temp_output_dir: str, templates: list):
        super().__init__()
        self.original_pdf_path = original_pdf_path
        self.temp_output_dir = temp_output_dir
        self.templates = templates
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            name, ext = os.path.splitext(os.path.basename(self.original_pdf_path))
            temp_output_path = os.path.join(self.temp_output_dir, f"{name}_preview{ext}")
            
            total_redactions = 0
            print(f"DEBUG: PreviewRedactionTask: Processing {os.path.basename(self.original_pdf_path)}...")
            with fitz.open(self.original_pdf_path) as doc:
                for page in doc:
                    total_redactions += find_and_redact_on_page(page, self.templates, MATCH_THRESHOLD)

                doc.save(temp_output_path, garbage=4, deflate=True)
                print(f"DEBUG: PreviewRedactionTask: Saved temporary {os.path.basename(temp_output_path)} with {total_redactions} redactions.")

            self.signals.finished.emit({
                "original_path": self.original_pdf_path,
                "temp_output_path": temp_output_path,
                "redactions": total_redactions
            })
        except Exception as e:
            print(f"ERROR: PreviewRedactionTask failed for {os.path.basename(self.original_pdf_path)}: {e}")
            self.signals.error.emit(f"Fehler bei Vorschau '{os.path.basename(self.original_pdf_path)}': {e}")


# ==============================================================================
#      DrawingCanvas für die Templaterstellung 
# ==============================================================================

class DrawingCanvas(QLabel):
    """
    Ein spezialisiertes QLabel-Widget, das das Anzeigen, Zoomen, Pannen
    und Markieren des Bildes übernimmt.
    Referenziert den Haupt-App-State für Bild, Rechtecke, Zoom/Pan-Status.
    """

    def __init__(self, main_app_instance: 'DarkMarkApp'): 
        super().__init__(main_app_instance) 
        self.main_app = main_app_instance
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #333; border: 1px solid gray;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def paintEvent(self, event):
        super().paintEvent(event)

        # Zugreifen auf den State der Haupt-App
        template_pixmap = self.main_app.state["template_canvas_pixmap"]
        rectangles = self.main_app.state["template_canvas_rects"]
        zoom_factor = self.main_app.state["template_canvas_zoom"]
        pan_offset = self.main_app.state["template_canvas_pan_offset"]
        drawing = self.main_app.state["template_canvas_drawing"]
        start_point_orig = self.main_app.state["template_canvas_start_point_orig"]
        end_point_orig = self.main_app.state["template_canvas_end_point_orig"]

        if not template_pixmap:
            self.setText("Bitte importieren Sie eine PDF-Datei zum Markieren.")
            return

        self.setText("")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.translate(pan_offset)
        painter.scale(zoom_factor, zoom_factor)

        painter.drawPixmap(QPointF(0, 0), template_pixmap)

        pen = QPen(Qt.GlobalColor.red, 2 / zoom_factor, Qt.PenStyle.SolidLine)
        painter.setPen(pen)

        if rectangles:
            painter.drawRects(rectangles)

        if drawing:
            current_rect = QRectF(start_point_orig, end_point_orig).normalized()
            painter.drawRect(current_rect)

    def map_widget_to_image(self, widget_pos: QPointF) -> QPointF:
        """Wandelt Widget-Koordinaten in Originalbild-Koordinaten um."""
        zoom_factor = self.main_app.state["template_canvas_zoom"]
        pan_offset = self.main_app.state["template_canvas_pan_offset"]
        return (widget_pos - pan_offset) / zoom_factor

    def wheelEvent(self, event: QWheelEvent):
        zoom_factor_step = 1.15
        pos = event.position()
        image_pos_before_zoom = self.map_widget_to_image(pos)

        if event.angleDelta().y() > 0:
            self.main_app.state["template_canvas_zoom"] *= zoom_factor_step
        else:
            self.main_app.state["template_canvas_zoom"] /= zoom_factor_step

        self.main_app.state["template_canvas_zoom"] = max(0.05, min(self.main_app.state["template_canvas_zoom"], 20.0))
        self.main_app.state["template_canvas_pan_offset"] = pos - image_pos_before_zoom * self.main_app.state["template_canvas_zoom"]

        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        pos = event.position()
        if event.button() == Qt.MouseButton.MiddleButton:
            self.main_app.state["template_canvas_panning"] = True
            self.main_app.state["template_canvas_last_pan_point"] = pos
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.LeftButton:
            self.main_app.state["template_canvas_drawing"] = True
            self.main_app.state["template_canvas_start_point_orig"] = self.map_widget_to_image(pos)
            self.main_app.state["template_canvas_end_point_orig"] = self.main_app.state["template_canvas_start_point_orig"]

        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()
        if self.main_app.state["template_canvas_panning"]:
            delta = pos - self.main_app.state["template_canvas_last_pan_point"]
            self.main_app.state["template_canvas_pan_offset"] += delta
            self.main_app.state["template_canvas_last_pan_point"] = pos
        elif self.main_app.state["template_canvas_drawing"]:
            self.main_app.state["template_canvas_end_point_orig"] = self.map_widget_to_image(pos)

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        pos = event.position()
        if event.button() == Qt.MouseButton.MiddleButton:
            self.main_app.state["template_canvas_panning"] = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif event.button() == Qt.MouseButton.LeftButton:
            self.main_app.state["template_canvas_drawing"] = False
            self.main_app.state["template_canvas_end_point_orig"] = self.map_widget_to_image(pos)

            new_rect = QRectF(self.main_app.state["template_canvas_start_point_orig"], self.main_app.state["template_canvas_end_point_orig"]).normalized()
            # Fester Pixelwert für minimale Größe im Canvas-Koordinatensystem
            if new_rect.width() > 5 and new_rect.height() > 5: 
                self.main_app.state["template_canvas_rects"].append(new_rect)
                self.main_app.save_template_button.setEnabled(True)
                self.main_app.undo_template_button.setEnabled(True)

        self.update()


# ==============================================================================
#      HAUPTANWENDUNG mit Mac-Look & erweiterter Funktionalität
# ==============================================================================

class DarkMarkApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DarkMark 1.1.0")
        self.setGeometry(100, 100, 1400, 900)
        self.setMinimumSize(1000, 700)

        self._set_macos_style_with_fallback()
        # KORRIGIERT: KEIN setWindowIcon HIER. Die QApplication wird es handhaben.
        # Entferne die PySide-Anweisung, damit das von PyInstaller eingebettete Icon Vorrang hat.
        # Das Problem liegt nicht darin, dass die Datei nicht gefunden wird, sondern wie Windows mit dem Laufzeit-Icon umgeht.
        # icon_path_ico = os.path.join(get_base_path(), "icon.ico")
        # icon_path_icns = os.path.join(get_base_path(), "icon.icns")
        # app = QApplication.instance()
        # if sys.platform == "darwin": 
        #     if os.path.exists(icon_path_icns):
        #         app.setWindowIcon(QIcon(icon_path_icns))
        #         print(f"DEBUG: macOS QApplication icon geladen von: {icon_path_icns}")
        #     else:
        #         print(f"WARNUNG: macOS icon.icns nicht gefunden unter: {icon_path_icns}")
        # else:
        #     if os.path.exists(icon_path_ico):
        #         # Dies ist die Zeile, die zu Problemen unter Windows führen kann
        #         # self.setWindowIcon(QIcon(icon_path_ico)) 
        #         print(f"DEBUG: Windows icon.ico sollte von PyInstaller eingebettet sein. Kein setWindowIcon im Code.")
        #     else:
        #         print(f"WARNUNG: Windows icon.ico nicht gefunden im PyInstaller-Bundle.")

        self.setAcceptDrops(True)

        self.state = {
            # --- Zustand für Schwärzungsmodus ---
            "current_mode": "redaction", # Startet immer im Schwärzungsmodus
            "original_doc": None,        
            "redacted_doc": None,        
            "original_pdf_paths": [],    
            "preview_pdf_paths": [],     
            "current_pdf_index": 0,
            "current_page_num": 0,       
            "is_processing": False,
            "is_in_preview_mode": False, 

            # --- Zustand für Templaterstellungsmodus ---
            "template_canvas_pdf_path": None, 
            "template_canvas_pixmap": None,   
            "template_canvas_rects": [],      
            "template_canvas_zoom": 1.0,      
            "template_canvas_pan_offset": QPointF(0, 0), 
            "template_canvas_panning": False, 
            "template_canvas_last_pan_point": QPointF(), 
            "template_canvas_drawing": False, 
            "template_canvas_start_point_orig": QPointF(), 
            "template_canvas_end_point_orig": QPointF(),   
        }
        self.templates_data = load_template_images(USER_TEMPLATES_PATH)
        self.thread_pool = QThreadPool()
        print(f"INFO: Thread-Pool mit {self.thread_pool.maxThreadCount()} Threads gestartet.")

        self.batch_files_to_process = 0
        self.batch_files_processed = 0
        self.batch_new_files = [] 

        self.preview_batch_total = 0
        self.preview_batch_processed = 0
        self.current_temp_preview_dir = None 

        self.main_widget = self._create_main_app_widget()
        self.setCentralWidget(self.main_widget)
        self.update_ui()


    def _set_macos_style_with_fallback(self):
        app = QApplication.instance()
        macos_style_found = False
        if sys.platform == "darwin": 
            for style_key in QStyleFactory.keys():
                if style_key == "Macintosh":
                    app.setStyle(QStyleFactory.create("Macintosh"))
                    macos_style_found = True
                    print("INFO: Macintosh-Stil angewendet.")
                    break
        if not macos_style_found:
            try:
                app.setStyle(QStyleFactory.create("Fusion"))
                print("INFO: Macintosh-Stil nicht gefunden oder nicht macOS. Fallback auf Fusion-Stil angewendet.")
            except Exception:
                print("INFO: Fusion-Stil nicht verfügbar. Verwende Systemstandard-Stil.")
        app.setPalette(app.style().standardPalette())
        app.setStyleSheet("") 

    def _create_main_app_widget(self) -> QWidget:
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # --- Linkes Steuerungs-Panel ---
        left_panel = QWidget()
        left_panel.setFixedWidth(350)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(15)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Header mit logo
        header_layout = QHBoxLayout()
        icon_label = QLabel()

        logo_path = os.path.join(get_base_path(), "assets", "logo.png")

        if os.path.exists(logo_path):
            logo_pixmap = QPixmap(logo_path)
            icon_label.setPixmap(logo_pixmap.scaled(
                60, 60,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        else:
            print(f"WARNUNG: Logo-Datei nicht gefunden unter: {logo_path}")
            icon_label.setPixmap(qta.icon('fa5s.user-secret', color='#00AEEF').pixmap(32, 32))

        title_label = QLabel("DarkMark")
        title_label.setObjectName("HeaderLabel") 

        header_layout.addWidget(icon_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        left_layout.addLayout(header_layout)
        #Header Ende

        # GEÄNDERT: tpl_status_label als Instanzattribut
        self.tpl_status = QLabel("") 
        self.tpl_status.setStyleSheet(f"color: #4CAF50; font-style: italic;") 
        self.tpl_status.setWordWrap(True)
        left_layout.addWidget(self.tpl_status)

        # --- Schwärzungs-Modus UI-Elemente (Gruppe) ---
        self.redaction_ui_group = QWidget()
        redaction_ui_layout = QVBoxLayout(self.redaction_ui_group)
        redaction_ui_layout.setContentsMargins(0, 0, 0, 0) 

        file_box = QGroupBox("1. Quelle auswählen")
        file_box_layout = QHBoxLayout()
        self.single_pdf_button = QPushButton(qta.icon('fa5.file-pdf'), " Einzelne PDF")
        self.single_pdf_button.clicked.connect(self.pick_single_pdf)
        self.folder_button = QPushButton(qta.icon('fa5.folder-open'), " Ganzer Ordner")
        self.folder_button.clicked.connect(self.pick_folder)
        file_box_layout.addWidget(self.single_pdf_button)
        file_box_layout.addWidget(self.folder_button)
        file_box.setLayout(file_box_layout)
        redaction_ui_layout.addWidget(file_box)

        self.status_label = QLabel("Bitte eine PDF-Datei oder einen Ordner auswählen (oder per Drag&Drop ziehen).")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("StatusLabel") 
        redaction_ui_layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        redaction_ui_layout.addWidget(self.progress_bar)

        nav_box = QGroupBox("Navigation")
        nav_layout = QVBoxLayout(nav_box)
        pdf_nav_layout = QHBoxLayout()
        self.prev_pdf_button = QPushButton(qta.icon('fa5s.chevron-left'), "")
        self.prev_pdf_button.clicked.connect(self.prev_pdf)
        self.pdf_info_label = QLabel("PDF: -/-")
        self.next_pdf_button = QPushButton(qta.icon('fa5s.chevron-right'), "")
        self.next_pdf_button.clicked.connect(self.next_pdf)
        pdf_nav_layout.addWidget(self.prev_pdf_button)
        pdf_nav_layout.addWidget(self.pdf_info_label, 1, Qt.AlignmentFlag.AlignCenter)
        pdf_nav_layout.addWidget(self.next_pdf_button)
        nav_layout.addLayout(pdf_nav_layout)

        page_nav_layout = QHBoxLayout()
        self.prev_page_button = QPushButton(qta.icon('fa5s.arrow-left'), "")
        self.prev_page_button.clicked.connect(self.prev_page)
        self.page_info_label = QLabel("Seite: -/-")
        self.next_page_button = QPushButton(qta.icon('fa5s.arrow-right'), "")
        self.next_page_button.clicked.connect(self.next_page)
        page_nav_layout.addWidget(self.prev_page_button)
        page_nav_layout.addWidget(self.page_info_label, 1, Qt.AlignmentFlag.AlignCenter)
        page_nav_layout.addWidget(self.next_page_button)
        nav_layout.addLayout(page_nav_layout)

        redaction_ui_layout.addWidget(nav_box)

        action_box = QGroupBox("2. Aktion ausführen")
        action_layout = QVBoxLayout(action_box)
        self.redact_preview_button = QPushButton(qta.icon('fa5s.eye-slash'), " Alle PDFs schwärzen (Vorschau)")
        self.redact_preview_button.setObjectName("AccentButton") 
        self.redact_preview_button.clicked.connect(self.start_batch_preview_redaction)
        action_layout.addWidget(self.redact_preview_button)

        self.save_button = QPushButton(qta.icon('fa5s.save'), " Vorschau speichern")
        self.save_button.clicked.connect(self.save_redacted_preview)
        action_layout.addWidget(self.save_button)
        action_layout.addWidget(self._create_separator())
        
        self.exit_preview_button = QPushButton(qta.icon('fa5s.undo'), " Zurück zu Original-PDFs")
        self.exit_preview_button.clicked.connect(self.go_to_original_mode)
        action_layout.addWidget(self.exit_preview_button)

        self.redact_all_button = QPushButton(qta.icon('fa5s.rocket'), " Alle PDFs verarbeiten & speichern")
        self.redact_all_button.setObjectName("AccentButton")
        self.redact_all_button.clicked.connect(self.redact_all_pdfs_batch)
        action_layout.addWidget(self.redact_all_button)
        redaction_ui_layout.addWidget(action_box)

        left_layout.addWidget(self.redaction_ui_group) 


        # --- Templaterstellungs-Modus UI-Elemente (Gruppe) ---
        self.template_ui_group = QWidget()
        template_ui_layout = QVBoxLayout(self.template_ui_group)
        template_ui_layout.setContentsMargins(0,0,0,0) 

        template_file_box = QGroupBox("1. PDF zum Markieren importieren")
        template_file_layout = QHBoxLayout(template_file_box)
        self.import_template_pdf_button = QPushButton(qta.icon('fa5.file-pdf'), " PDF importieren")
        self.import_template_pdf_button.clicked.connect(self.import_pdf_for_template_creation)
        template_file_layout.addWidget(self.import_template_pdf_button)
        template_ui_layout.addWidget(template_file_box)

        template_action_box = QGroupBox("2. Markierungen verwalten")
        template_action_layout = QVBoxLayout(template_action_box)
        self.undo_template_button = QPushButton(qta.icon('fa5s.eraser'), " Letzte Markierung entfernen")
        self.undo_template_button.clicked.connect(self.undo_last_template_rectangle)
        self.undo_template_button.setEnabled(False)
        template_action_layout.addWidget(self.undo_template_button)

        self.save_template_button = QPushButton(qta.icon('fa5s.save'), " Markierte Bereiche als Templates speichern")
        self.save_template_button.setObjectName("AccentButton")
        self.save_template_button.clicked.connect(self.save_marked_areas_as_templates)
        self.save_template_button.setEnabled(False)
        template_action_layout.addWidget(self.save_template_button)

        # Button zum Zurückkehren zum Schwärzungsmodus aus dem Template-Modus
        self.return_to_redaction_button = QPushButton(qta.icon('fa5s.arrow-alt-circle-left'), " Zurück zum Schwärzen")
        self.return_to_redaction_button.clicked.connect(lambda: self.switch_mode("redaction"))
        template_action_layout.addWidget(self.return_to_redaction_button)

        template_ui_layout.addWidget(template_action_box)
        template_ui_layout.addStretch(1) 

        # NEU: Templates laden und verwalten Buttons
        template_load_manage_box = QGroupBox("3. Templates verwalten")
        template_load_manage_layout = QVBoxLayout(template_load_manage_box)

        self.reload_user_templates_button = QPushButton(qta.icon('fa5s.sync-alt'), " Templates neu laden") 
        self.reload_user_templates_button.clicked.connect(self.reload_templates_data_from_disk)
        template_load_manage_layout.addWidget(self.reload_user_templates_button)

        self.import_templates_button = QPushButton(qta.icon('fa5s.file-import'), " Templates importieren (Ordner wählen)")
        self.import_templates_button.clicked.connect(self.import_templates_from_folder)
        template_load_manage_layout.addWidget(self.import_templates_button)

        self.backup_templates_button = QPushButton(qta.icon('fa5s.archive'), " Templates sichern (Ordner wählen)")
        self.backup_templates_button.clicked.connect(self.backup_user_templates)
        template_load_manage_layout.addWidget(self.backup_templates_button)

        self.clear_user_templates_button = QPushButton(qta.icon('fa5s.trash-alt'), " Alle Templates löschen")
        self.clear_user_templates_button.clicked.connect(self.clear_user_templates_data)
        template_load_manage_layout.addWidget(self.clear_user_templates_button)
        
        template_ui_layout.addWidget(template_load_manage_box)
        template_ui_layout.addStretch(1) 


        left_layout.addWidget(self.template_ui_group) 


        left_layout.addStretch(1) # Flexibler Abstand

        # "Templates verwalten" Button ganz unten
        self.manage_templates_button = QPushButton(qta.icon('fa5s.user-secret'), " Templates verwalten (Passwort)")
        self.manage_templates_button.setObjectName("AccentButton")
        self.manage_templates_button.clicked.connect(self.show_template_management_dialog)
        left_layout.addWidget(self.manage_templates_button)

        # Footer (bleibt am unteren Rand)
        footer_label = QLabel("© Johannes Gschwendtner")
        footer_label.setStyleSheet("color: #6A6A6A; font-size: 8pt;") 
        left_layout.addWidget(footer_label, 0, Qt.AlignmentFlag.AlignBottom)

        main_layout.addWidget(left_panel)


        # --- Rechter Anzeige-Bereich (QStackedWidget) ---
        self.stacked_display_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_display_widget, 1)

        # Schwärzungsmodus-Ansicht
        self.redaction_display_frame = QFrame()
        self.redaction_display_frame.setObjectName("Card") 
        redaction_display_layout = QVBoxLayout(self.redaction_display_frame)
        self.pdf_image_label = QLabel("...")
        self.pdf_image_label.setObjectName("Placeholder") 
        self.pdf_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        redaction_display_layout.addWidget(self.pdf_image_label)
        self.stacked_display_widget.addWidget(self.redaction_display_frame) # Index 0

        # Templaterstellungsmodus-Ansicht
        self.template_canvas = DrawingCanvas(self) 
        self.stacked_display_widget.addWidget(self.template_canvas) # Index 1

        # Standardmäßig den Schwärzungsmodus anzeigen
        self.stacked_display_widget.setCurrentIndex(0) 

        return main_widget

    def _create_separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        return sep

    # ==========================================================================
    #     Modus-Wechsel-Logik (Angepasst)
    # ==========================================================================

    def show_template_management_dialog(self):
        if self.state["is_processing"]:
            QMessageBox.warning(self, "Verarbeitung läuft", "Bitte warten Sie, bis die aktuelle Verarbeitung abgeschlossen ist.")
            return

        password, ok = QInputDialog.getText(
            self, 
            "Passwort benötigt", 
            "Bitte geben Sie das Passwort für die Template-Verwaltung ein:",
            QLineEdit.Password # Macht die Eingabe verdeckt
        )

        if ok and password == "Sessel":
            self.switch_mode("template_creation")
        elif ok: # OK gedrückt, aber Passwort falsch
            QMessageBox.warning(self, "Falsches Passwort", "Das eingegebene Passwort ist nicht korrekt.")


    @Slot(str)
    def switch_mode(self, mode: str):
        if self.state["is_processing"]:
            QMessageBox.warning(self, "Verarbeitung läuft", "Bitte warten Sie, bis die aktuelle Verarbeitung abgeschlossen ist.")
            return

        self.state["current_mode"] = mode
        print(f"DEBUG: Switched to mode: {mode}")

        self.clear_all_docs_except_templates() 
        
        if mode == "redaction":
            self.stacked_display_widget.setCurrentIndex(0) # Schwärzungsansicht aktivieren
            self.redaction_ui_group.setVisible(True) 
            self.template_ui_group.setVisible(False) 

            self.templates_data = load_template_images(USER_TEMPLATES_PATH) 
            if self.state["original_pdf_paths"]:
                self.state["current_pdf_index"] = 0
                self._load_pdf_into_state(self.state["original_pdf_paths"][0], "original_doc")
            

        elif mode == "template_creation":
            self.stacked_display_widget.setCurrentIndex(1) # Templaterstellungsansicht aktivieren
            self.redaction_ui_group.setVisible(False) 
            self.template_ui_group.setVisible(True) 
            
            self.reset_template_canvas() 

        self.update_ui()


    # ==========================================================================
    #     Allgemeine UI-Aktualisierung & Dokumenten-Management
    # ==========================================================================

    def update_ui(self):
        is_processing = self.state["is_processing"]
        is_in_redaction_mode = (self.state["current_mode"] == "redaction")
        is_in_template_mode = (self.state["current_mode"] == "template_creation")

        self.redaction_ui_group.setVisible(is_in_redaction_mode)
        self.template_ui_group.setVisible(is_in_template_mode)
        
        self.manage_templates_button.setEnabled(not is_processing)

        # Aktuellen Template-Status des Labels aktualisieren
        tpl_status_text = (f"{len(self.templates_data)} Templates geladen." if self.templates_data
                           else f"Warnung: Keine Templates gefunden!")
        tpl_status_color = "#4CAF50" if self.templates_data else "#FFC107"
        self.tpl_status.setText(tpl_status_text)
        self.tpl_status.setStyleSheet(f"color: {tpl_status_color}; font-style: italic;")


        if is_in_redaction_mode:
            has_original_docs = bool(self.state["original_pdf_paths"])
            has_redacted_preview = bool(self.state["preview_pdf_paths"])
            is_in_preview_mode = self.state["is_in_preview_mode"]

            doc_to_show = self.state["redacted_doc"] if is_in_preview_mode else self.state["original_doc"]

            if doc_to_show and self.pdf_image_label.width() > 1:
                page_num = self.state.get("current_page_num", 0)
                pixmap = page_to_pixmap(doc_to_show, page_num, self.pdf_image_label.size())
                if pixmap:
                    self.pdf_image_label.setPixmap(pixmap)
                    self.pdf_image_label.setObjectName("")
                else:
                    self.pdf_image_label.setPixmap(QPixmap())
                    self.pdf_image_label.setText(f"Fehler beim Rendern von Seite {page_num + 1}")
                    self.pdf_image_label.setObjectName("Placeholder")
                self.page_info_label.setText(f"Seite: {page_num + 1}/{doc_to_show.page_count}")
            else:
                self.pdf_image_label.setPixmap(QPixmap())
                self.pdf_image_label.setText("Bitte PDF-Datei oder Ordner auswählen (oder per Drag&Drop ziehen).")
                self.pdf_image_label.setObjectName("Placeholder")
                self.page_info_label.setText("Seite: -/-")

            current_display_paths_list = self.state["preview_pdf_paths"] if is_in_preview_mode else self.state["original_pdf_paths"]
            if current_display_paths_list:
                self.pdf_info_label.setText(f"PDF: {self.state['current_pdf_index'] + 1} / {len(current_display_paths_list)}")
            else:
                self.pdf_info_label.setText("PDF: -/-")

            self.single_pdf_button.setEnabled(not is_processing and not is_in_preview_mode) 
            self.folder_button.setEnabled(not is_processing and not is_in_preview_mode) 
            
            self.prev_pdf_button.setEnabled(bool(not is_processing and self.state["current_pdf_index"] > 0 and current_display_paths_list))
            self.next_pdf_button.setEnabled(
                bool(not is_processing and current_display_paths_list and self.state["current_pdf_index"] < len(current_display_paths_list) - 1))

            current_page_num = self.state.get("current_page_num", 0)
            page_count = doc_to_show.page_count if doc_to_show else 0
            self.prev_page_button.setEnabled(bool(not is_processing and doc_to_show and current_page_num > 0))
            self.next_page_button.setEnabled(
                bool(not is_processing and doc_to_show and current_page_num < page_count - 1))

            self.redact_preview_button.setEnabled(bool(not is_processing and has_original_docs and self.templates_data and not is_in_preview_mode)) 
            
            self.save_button.setEnabled(bool(not is_processing and is_in_preview_mode and has_redacted_preview)) 
            
            self.redact_all_button.setEnabled(
                bool(not is_processing and has_original_docs and self.templates_data and not is_in_preview_mode)) 

            self.exit_preview_button.setEnabled(bool(not is_processing and is_in_preview_mode))

            self.progress_bar.setVisible(is_processing) 
            self.status_label.setVisible(True) 
        
        elif is_in_template_mode:
            has_template_pdf = bool(self.state["template_canvas_pdf_path"])
            has_template_rects = bool(self.state["template_canvas_rects"])
            
            self.import_template_pdf_button.setEnabled(not is_processing)
            self.undo_template_button.setEnabled(not is_processing and has_template_rects)
            self.save_template_button.setEnabled(not is_processing and has_template_rects)
            self.return_to_redaction_button.setEnabled(not is_processing) 

            # NEU: Buttons für Template-Verwaltung im Template-Modus
            templates_in_user_dir = len([f for f in os.listdir(USER_TEMPLATES_PATH) if os.path.isfile(os.path.join(USER_TEMPLATES_PATH, f))]) \
                                     if os.path.exists(USER_TEMPLATES_PATH) else 0

            self.reload_user_templates_button.setEnabled(not is_processing) 
            self.import_templates_button.setEnabled(not is_processing) 
            self.backup_templates_button.setEnabled(not is_processing and templates_in_user_dir > 0)
            self.clear_user_templates_button.setEnabled(not is_processing and templates_in_user_dir > 0)

            self.progress_bar.setVisible(False) 
            self.status_label.setText("Bitte PDF zum Markieren importieren.")
            self.status_label.setVisible(True) 

        if is_in_template_mode:
            self.template_canvas.update()


    def _clear_temp_preview_files(self):
        print(f"DEBUG: _clear_temp_preview_files called. Current temp dir: {self.current_temp_preview_dir}")
        if self.current_temp_preview_dir and os.path.exists(self.current_temp_preview_dir):
            try:
                shutil.rmtree(self.current_temp_preview_dir, ignore_errors=True)
                print(f"DEBUG: Temporäres Vorschau-Verzeichnis gelöscht: {self.current_temp_preview_dir}")
            except Exception as e:
                print(f"WARNUNG: Fehler beim Löschen des temporären Vorschau-Verzeichnisses {self.current_temp_preview_dir}: {e}")
        self.current_temp_preview_dir = None
        self.state["preview_pdf_paths"].clear()
        self.state["is_in_preview_mode"] = False


    def clear_all_docs_except_templates(self):
        """
        Schließt alle geöffneten PyMuPDF-Dokumente und löscht Verweise für den Schwärzungsmodus.
        Behält aber die Templaterstellungs-Daten bei.
        """
        print("DEBUG: clear_all_docs_except_templates called.")
        if self.state["original_doc"]: 
            self.state["original_doc"].close()
            self.state["original_doc"] = None
        if self.state["redacted_doc"]: 
            self.state["redacted_doc"].close()
            self.state["redacted_doc"] = None
            
        self.state["original_pdf_paths"].clear() 
        self.state["current_pdf_index"] = 0
        self.state["current_page_num"] = 0 

        self._clear_temp_preview_files() 


    def clear_all_docs(self):
        """
        Führt einen vollständigen Reset der Anwendung durch, inklusive
        Löschen aller Dokumentenreferenzen und Templaterstellungsdaten.
        """
        print("DEBUG: clear_all_docs (full reset) called.")
        self.clear_all_docs_except_templates() 
        
        self.reset_template_canvas() 


    def reset_template_canvas(self):
        """Setzt den Zustand des Templaterstellungs-Canvas vollständig zurück."""
        print(f"DEBUG: reset_template_canvas called (clearing template_canvas_pdf_path: {self.state['template_canvas_pdf_path']}).")
        self.state["template_canvas_pdf_path"] = None
        self.state["template_canvas_pixmap"] = None
        self.state["template_canvas_rects"] = []
        self.state["template_canvas_zoom"] = 1.0
        self.state["template_canvas_pan_offset"] = QPointF(0, 0)
        self.state["template_canvas_panning"] = False
        self.state["template_canvas_last_pan_point"] = QPointF()
        self.state["template_canvas_drawing"] = False
        self.state["template_canvas_start_point_orig"] = QPointF()
        self.state["template_canvas_end_point_orig"] = QPointF()
        self.template_canvas.update() 


    def _load_pdf_into_state(self, pdf_path: str, target_state_key: str):
        """
        Lädt eine PDF-Datei in den angegebenen Zustandsschlüssel (z.B. 'original_doc' oder 'redacted_doc').
        Schließt zuvor das jeweils andere Dokument, um Ressourcen freizugeben.
        """
        if target_state_key == "original_doc":
            if self.state["redacted_doc"]:
                self.state["redacted_doc"].close()
                self.state["redacted_doc"] = None
            self.state["original_doc"] = fitz.open(pdf_path)
            print(f"DEBUG: Loaded original_doc: {os.path.basename(pdf_path)}")
        elif target_state_key == "redacted_doc":
            if self.state["original_doc"]:
                self.state["original_doc"].close()
                self.state["original_doc"] = None
            self.state["redacted_doc"] = fitz.open(pdf_path)
            print(f"DEBUG: Loaded redacted_doc (preview): {os.path.basename(pdf_path)}")
        else:
            raise ValueError("Ungültiger target_state_key. Muss 'original_doc' oder 'redacted_doc' sein.")
        
        self.state["current_page_num"] = 0 


    def _handle_pdf_paths(self, pdf_paths: List[str], source_description: str = ""):
        if not pdf_paths:
            QMessageBox.information(self, "Information", "Keine PDF-Dateien zum Laden gefunden.")
            return

        valid_pdf_paths = [p for p in pdf_paths if os.path.isfile(p) and p.lower().endswith('.pdf')]

        if not valid_pdf_paths:
            QMessageBox.warning(self, "Warnung", f"Keine gültigen PDF-Dateien im {source_description} gefunden.")
            return
        
        self.clear_all_docs_except_templates() 

        self.state["original_pdf_paths"] = sorted(valid_pdf_paths)
        self.state["current_pdf_index"] = 0
        self.state["current_page_num"] = 0 

        try:
            self._load_pdf_into_state(self.state["original_pdf_paths"][0], "original_doc")
            self.status_label.setText(f"Controller: {len(valid_pdf_paths)} PDF(s) {source_description} geladen.") 
        except Exception as e:
            QMessageBox.critical(self, "Ladefehler", f"Fehler beim Laden der PDF:\n{e}")
            self.status_label.setText(f"Fehler beim Laden.")
            self.clear_all_docs_except_templates() 
        self.update_ui()


    def pick_single_pdf(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "PDF-Datei auswählen", "", "PDF-Dateien (*.pdf)")
        if filepath:
            self._handle_pdf_paths([filepath], "manuell")

    def pick_folder(self):
        folderpath = QFileDialog.getExistingDirectory(self, "Ordner mit PDFs auswählen")
        if folderpath:
            pdf_files = [os.path.join(folderpath, f) for f in os.listdir(folderpath) if f.lower().endswith('.pdf')]
            self._handle_pdf_paths(pdf_files, "aus Ordner")


    def prev_page(self):
        doc_to_navigate = self.state["redacted_doc"] if self.state["is_in_preview_mode"] else self.state["original_doc"]
        if doc_to_navigate and self.state.get("current_page_num", 0) > 0:
            self.state["current_page_num"] -= 1;
            self.update_ui()

    def next_page(self):
        doc_to_navigate = self.state["redacted_doc"] if self.state["is_in_preview_mode"] else self.state["original_doc"]
        if doc_to_navigate and self.state.get("current_page_num", 0) < doc_to_navigate.page_count - 1:
            self.state["current_page_num"] += 1;
            self.update_ui()

    def prev_pdf(self):
        current_paths = self.state["preview_pdf_paths"] if self.state["is_in_preview_mode"] else self.state["original_pdf_paths"]

        if self.state["current_pdf_index"] > 0:
            self.state["current_pdf_index"] -= 1;
            self.load_pdf_for_display(current_paths[self.state["current_pdf_index"]]) 

    def next_pdf(self):
        current_paths = self.state["preview_pdf_paths"] if self.state["is_in_preview_mode"] else self.state["original_pdf_paths"]

        if self.state["current_pdf_index"] < len(current_paths) - 1:
            self.state["current_pdf_index"] += 1;
            self.load_pdf_for_display(current_paths[self.state["current_pdf_index"]]) 

    def load_pdf_for_display(self, pdf_path: str):
        try:
            if self.state["is_in_preview_mode"]:
                self._load_pdf_into_state(pdf_path, "redacted_doc") 
            else:
                self._load_pdf_into_state(pdf_path, "original_doc")
                
            self.status_label.setText(f"Anzeige: {os.path.basename(pdf_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Anzeigefehler", f"Fehler beim Laden der PDF zur Anzeige:\n{e}")
            self.status_label.setText(f"Fehler beim Laden.")
            if self.state["is_in_preview_mode"]:
                self.state["redacted_doc"] = None
            else:
                self.state["original_doc"] = None
        self.update_ui()


    def start_batch_preview_redaction(self):
        if not self.state["original_pdf_paths"]: 
            QMessageBox.information(self, "Keine PDFs", "Bitte zuerst PDF-Dateien laden.")
            return
        if not self.templates_data:
            QMessageBox.warning(self, "Keine Templates", "Es wurden keine Schwärzungs-Templates gefunden.")
            return

        self.state["is_processing"] = True
        self._clear_temp_preview_files() 
        
        self.current_temp_preview_dir = tempfile.mkdtemp(prefix="darkmark_preview_")
        print(f"DEBUG: Temporäres Vorschau-Verzeichnis erstellt: {self.current_temp_preview_dir}")

        self.preview_batch_total = len(self.state["original_pdf_paths"])
        self.preview_batch_processed = 0
        self.state["preview_pdf_paths"].clear() 
        
        self.progress_bar.setMaximum(self.preview_batch_total)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Vorschau-Schwärzung wird vorbereitet...")
        self.update_ui()

        for original_path in self.state["original_pdf_paths"]:
            task = PreviewRedactionTask(original_path, self.current_temp_preview_dir, self.templates_data)
            task.signals.finished.connect(self.on_preview_task_finished)
            task.signals.error.connect(self.on_preview_task_error)
            self.thread_pool.start(task)

    def on_preview_task_finished(self, result: dict):
        self.preview_batch_processed += 1
        self.state["preview_pdf_paths"].append(result["temp_output_path"])
        self.progress_bar.setValue(self.preview_batch_processed)
        self.status_label.setText(f"Vorschau verarbeitet: {os.path.basename(result['original_path'])}")
        self._check_preview_batch_completion()

    def on_preview_task_error(self, error_msg: str):
        self.preview_batch_processed += 1
        QMessageBox.warning(self, "Vorschaufehler", error_msg)
        self._check_preview_batch_completion()

    def _check_preview_batch_completion(self):
        if self.preview_batch_processed >= self.preview_batch_total:
            self.state["is_processing"] = False
            self.progress_bar.setVisible(False)
            
            if self.state["preview_pdf_paths"]:
                self.state["is_in_preview_mode"] = True 
                self.state["current_pdf_index"] = 0
                self.state["preview_pdf_paths"].sort() 
                self.load_pdf_for_display(self.state["preview_pdf_paths"][0]) 
                self.status_label.setText(f"Vorschau-Schwärzung abgeschlossen. {len(self.state['preview_pdf_paths'])} Dateien zum Ansehen bereit.")
            else:
                self.status_label.setText("Vorschau-Schwärzung abgeschlossen. Keine PDFs generiert (oder alle fehlgeschlagen).")
                self.clear_all_docs_except_templates() 

            self.update_ui()


    def save_redacted_preview(self):
        if not self.state["is_in_preview_mode"] or not self.state["preview_pdf_paths"]:
            QMessageBox.information(self, "Hinweis", "Keine geschwärzte Vorschau zum Speichern vorhanden.")
            return

        current_preview_path = self.state["preview_pdf_paths"][self.state["current_pdf_index"]]
        original_name = os.path.basename(current_preview_path).replace("_preview", "") 
        name, ext = os.path.splitext(original_name)
        
        if not ext: ext = ".pdf"
        elif ext.lower() != ".pdf": ext = ".pdf" 

        save_path, _ = QFileDialog.getSaveFileName(self, "Geschwärztes PDF speichern", f"{name}_geschwaerzt{ext}",
                                                   "PDF-Dateien (*.pdf)")
        if save_path:
            try:
                shutil.copy(current_preview_path, save_path)
                self.status_label.setText(f"Gespeichert: {os.path.basename(save_path)}")
            except Exception as e:
                QMessageBox.critical(self, "Speicherfehler", f"Ein Fehler ist aufgetreten:\n{e}")

    def redact_all_pdfs_batch(self):
        if not self.state["original_pdf_paths"]:
            QMessageBox.information(self, "Keine PDFs", "Bitte zuerst PDF-Dateien laden.")
            return
        if not self.templates_data:
            QMessageBox.warning(self, "Keine Templates", "Es wurden keine Schwärzungs-Templates gefunden.")
            return

        output_folder = QFileDialog.getExistingDirectory(self, "Ausgabeordner für geschwärzte PDFs wählen")
        if not output_folder: return

        self.state["is_processing"] = True
        if self.state["is_in_preview_mode"]:
            self.go_to_original_mode() 
        
        self.batch_files_to_process = len(self.state["original_pdf_paths"])
        self.batch_files_processed = 0
        self.batch_new_files.clear()
        self.progress_bar.setMaximum(self.batch_files_to_process)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Finale Stapelverarbeitung läuft...")
        self.update_ui()

        for in_path in self.state["original_pdf_paths"]:
            name, ext = os.path.splitext(os.path.basename(in_path))
            out_path = os.path.join(output_folder, f"{name}_geschwaerzt{ext}")
            task = RedactionTask(in_path, out_path, self.templates_data)
            task.signals.finished.connect(self.on_batch_task_finished)
            task.signals.error.connect(self.on_batch_task_error)
            self.thread_pool.start(task)

    def on_batch_task_finished(self, result: dict):
        self.batch_files_processed += 1
        if result["redactions"] > 0:
            self.batch_new_files.append(result["output_path"])
        self.progress_bar.setValue(self.batch_files_processed)
        self.status_label.setText(f"Verarbeitet: {os.path.basename(result['input_path'])}")
        self._check_batch_completion()

    def on_batch_task_error(self, error_msg: str):
        self.batch_files_processed += 1
        QMessageBox.warning(self, "Verarbeitungsfehler", error_msg)
        self._check_batch_completion()

    def _check_batch_completion(self):
        if self.batch_files_processed >= self.batch_files_to_process:
            self.state["is_processing"] = False
            self.progress_bar.setVisible(False)
            self.status_label.setText(
                f"Stapelverarbeitung abgeschlossen. {len(self.batch_new_files)} Dateien gespeichert.")
            QMessageBox.information(self, "Fertig",
                                    f"Alle {self.batch_files_to_process} PDF-Dateien wurden verarbeitet.")

            self.clear_all_docs() 
            self.update_ui()

    def closeEvent(self, event):
        if self.state["is_processing"]:
            QMessageBox.warning(self, "Verarbeitung läuft",
                                "Bitte warten Sie, bis die Stapelverarbeitung abgeschlossen ist.")
            event.ignore()
            return

        reply = QMessageBox.question(self, 'Beenden', "Möchten Sie DarkMark wirklich beenden?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.clear_all_docs() 
            self.thread_pool.clear()
            self.thread_pool.waitForDone()
            # GEÄNDERT: TEMP_IMAGE_DIR_GLOBAL entfernt
            # if os.path.exists(TEMP_IMAGE_DIR_GLOBAL): 
            #     shutil.rmtree(TEMP_IMAGE_DIR_GLOBAL, ignore_errors=True)
            event.accept()
        else:
            event.ignore()

    # ==========================================================================
    #     DRAG-AND-DROP-METHODEN (Anpassungen für Modus-Trennung)
    # ==========================================================================

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self.state["is_processing"] or self.state["current_mode"] != "redaction":
            event.ignore()
            return
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and url.toLocalFile().lower().endswith('.pdf'):
                    event.acceptProposedAction() 
                    return
        event.ignore()

    def dragMoveEvent(self, event: QDragEnterEvent):
        if self.state["current_mode"] != "redaction":
            event.ignore()
            return
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        if self.state["is_processing"] or self.state["current_mode"] != "redaction":
            event.ignore()
            return

        if event.mimeData().hasUrls():
            dropped_pdf_paths = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith('.pdf'):
                        dropped_pdf_paths.append(file_path)
                    elif os.path.isdir(file_path):
                        for root, _, files in os.walk(file_path):
                            for f in files:
                                if f.lower().endswith('.pdf'):
                                    dropped_pdf_paths.append(os.path.join(root, f))

            if dropped_pdf_paths:
                self._handle_pdf_paths(dropped_pdf_paths, "per Drag&Drop")
                event.acceptProposedAction()
            else:
                QMessageBox.warning(self, "Keine PDF gefunden",
                                    "Die gezogenen Elemente enthalten keine gültigen PDF-Dateien.")
                event.ignore()
        else:
            event.ignore()


    def go_to_original_mode(self):
        if not self.state["is_in_preview_mode"]: 
            return
        
        self.state["is_in_preview_mode"] = False
        self._clear_temp_preview_files() 

        if self.state["redacted_doc"]:
            self.state["redacted_doc"].close()
            self.state["redacted_doc"] = None

        if self.state["original_pdf_paths"]:
            self.state["current_pdf_index"] = 0 
            try:
                self._load_pdf_into_state(self.state["original_pdf_paths"][self.state["current_pdf_index"]], "original_doc")
                self.status_label.setText(f"Zurück zu Original-PDFs. Vorschau-Dateien gelöscht.")
            except Exception as e:
                QMessageBox.critical(self, "Fehler", f"Fehler beim erneuten Laden des Original-PDFs:\n{e}")
                self.status_label.setText("Fehler beim Zurückwechseln.")
                self.clear_all_docs_except_templates() 
        else:
            self.clear_all_docs_except_templates() 
            self.status_label.setText("Vorschau-Modus verlassen. Keine Original-PDFs mehr vorhanden.")

        self.update_ui()

    # ==========================================================================
    #     Templaterstellungs-Logik (Korrekturen und Konsistenz)
    # ==========================================================================

    def import_pdf_for_template_creation(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "PDF-Datei zum Markieren auswählen", "", "PDF-Dateien (*.pdf)"
        )
        if not file_path:
            return

        try:
            self.state["template_canvas_pdf_path"] = file_path 
            doc = fitz.open(self.state["template_canvas_pdf_path"])
            page = doc.load_page(0) 

            pix = page.get_pixmap(dpi=150) 

            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            self.state["template_canvas_pixmap"] = QPixmap.fromImage(image)
            doc.close()

            self.reset_template_canvas_view_and_rects()
            self.status_label.setText(f"PDF geladen für Templates: {os.path.basename(file_path)}")
            self.update_ui() 
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"PDF konnte nicht geladen werden:\n{e}")
            self.state["template_canvas_pdf_path"] = None
            self.state["template_canvas_pixmap"] = None
            self.reset_template_canvas_view_and_rects()
            self.update_ui() 


    def reset_template_canvas_view_and_rects(self):
        """Setzt Zoom/Pan zurück und löscht Markierungen im Templaterstellungs-Canvas."""
        self.state["template_canvas_rects"] = []
        self.state["template_canvas_panning"] = False
        self.state["template_canvas_last_pan_point"] = QPointF()

        if not self.state["template_canvas_pixmap"]:
            self.state["template_canvas_zoom"] = 1.0
            self.state["template_canvas_pan_offset"] = QPointF(0, 0)
            self.template_canvas.update()
            self.undo_template_button.setEnabled(False) 
            self.save_template_button.setEnabled(False) 
            return

        w_ratio = self.template_canvas.width() / self.state["template_canvas_pixmap"].width()
        h_ratio = self.template_canvas.height() / self.state["template_canvas_pixmap"].height()
        self.state["template_canvas_zoom"] = min(w_ratio, h_ratio, 1.0) 

        self.state["template_canvas_pan_offset"] = QPointF(
            (self.template_canvas.width() - self.state["template_canvas_pixmap"].width() * self.state["template_canvas_zoom"]) / 2,
            (self.template_canvas.height() - self.state["template_canvas_pixmap"].height() * self.state["template_canvas_zoom"]) / 2
        )
        self.template_canvas.update()
        self.undo_template_button.setEnabled(False) 
        self.save_template_button.setEnabled(False) 

    def undo_last_template_rectangle(self):
        """Entfernt das zuletzt gezeichnete Rechteck im Templaterstellungsmodus."""
        if self.state["template_canvas_rects"]:
            self.state["template_canvas_rects"].pop()
            self.template_canvas.update()

            if not self.state["template_canvas_rects"]:
                self.undo_template_button.setEnabled(False)
                self.save_template_button.setEnabled(False)
            self.update_ui()


    def save_marked_areas_as_templates(self):
        """
        Speichert jeden markierten Bereich als separate 300-DPI-PNG-Datei
        im BENUTZERSPEZIFISCHEN TEMPLATE_DIR_PATH.
        """
        if not self.state["template_canvas_rects"] or not self.state["template_canvas_pdf_path"]:
            QMessageBox.warning(self, "Warnung", "Keine Markierungen zum Speichern vorhanden oder PDF nicht geladen.")
            return

        dir_path = USER_TEMPLATES_PATH 

        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path)
                print(f"DEBUG: Benutzer-Template-Speicherordner erstellt: {dir_path}")
            except OSError as e:
                QMessageBox.critical(self, "Fehler", f"Konnte Speicherordner für Templates nicht erstellen: {e}")
                return

        try:
            doc = fitz.open(self.state["template_canvas_pdf_path"])
            page = doc.load_page(0)

            pdf_page_rect = page.rect
            pixmap_size = self.state["template_canvas_pixmap"].size()

            if pixmap_size.width() == 0 or pixmap_size.height() == 0:
                raise ValueError("Anzeigebild hat eine ungültige Größe.")

            scale_x = pdf_page_rect.width / pixmap_size.width()
            scale_y = pdf_page_rect.height / pixmap_size.height()

            export_dpi = 300 
            saved_count = 0

            for i, rect in enumerate(self.state["template_canvas_rects"]):
                fitz_rect = fitz.Rect(
                    rect.left() * scale_x,
                    rect.top() * scale_y,
                    rect.right() * scale_x,
                    rect.bottom() * scale_y
                )

                pix = page.get_pixmap(dpi=export_dpi, clip=fitz_rect)

                base_name = os.path.splitext(os.path.basename(self.state["template_canvas_pdf_path"]))[0]
                output_filename = f"{base_name}_template_{i + 1}.png"
                output_path = os.path.join(dir_path, output_filename)

                pix.save(output_path)
                saved_count += 1

            doc.close()
            QMessageBox.information(self, "Erfolg",
                                    f"{saved_count} Template-Ausschnitte erfolgreich gespeichert im Ordner:\n'{dir_path}'\n\nDie Templates werden beim nächsten Start oder Moduswechsel geladen.")

            self.reset_template_canvas_view_and_rects() 
            self.state["template_canvas_pdf_path"] = None 
            self.state["template_canvas_pixmap"] = None
            self.template_canvas.update()
            self.update_ui()

        except Exception as e:
            QMessageBox.critical(self, "Fehler beim Speichern", f"Ein Fehler ist aufgetreten:\n{e}")

    def resizeEvent(self, event):
        """Wenn Fenstergröße geändert wird, Ansicht neu zentrieren."""
        super().resizeEvent(event)
        if self.state["current_mode"] == "template_creation":
            self.reset_template_canvas_view_and_rects()

    # NEU: Methode zum Neuladen der Templates aus dem Benutzerverzeichnis
    @Slot()
    def reload_templates_data_from_disk(self):
        """Lädt die Templates neu aus dem USER_TEMPLATES_PATH."""
        if self.state["is_processing"]:
            QMessageBox.warning(self, "Verarbeitung läuft", "Bitte warten Sie, bis die aktuelle Verarbeitung abgeschlossen ist.")
            return
        
        self.templates_data = load_template_images(USER_TEMPLATES_PATH)
        self.status_label.setText(f"Templates neu geladen: {len(self.templates_data)} gefunden.")
        QMessageBox.information(self, "Templates neu geladen", 
                                f"{len(self.templates_data)} Templates aus '{USER_TEMPLATES_PATH}' erfolgreich geladen.")
        self.update_ui()

    # NEU: Methode zum Importieren von Templates aus einem Ordner in den USER_TEMPLATES_PATH
    @Slot()
    def import_templates_from_folder(self):
        if self.state["is_processing"]:
            QMessageBox.warning(self, "Verarbeitung läuft", "Bitte warten Sie, bis die aktuelle Verarbeitung abgeschlossen ist.")
            return
        
        source_dir = QFileDialog.getExistingDirectory(self, "Ordner mit Templates zum Importieren auswählen")
        if not source_dir:
            return

        imported_count = 0
        skipped_count = 0
        
        # Sicherstellen, dass der Zielordner existiert
        if not os.path.exists(USER_TEMPLATES_PATH):
            os.makedirs(USER_TEMPLATES_PATH, exist_ok=True)

        for filename in os.listdir(source_dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff')):
                src_path = os.path.join(source_dir, filename)
                dest_path = os.path.join(USER_TEMPLATES_PATH, filename)
                try:
                    # Kopieren, überschreibt existierende Dateien mit gleichem Namen
                    shutil.copy2(src_path, dest_path) 
                    imported_count += 1
                except Exception as e:
                    print(f"WARNUNG: Fehler beim Importieren von {filename}: {e}")
                    skipped_count += 1
        
        self.status_label.setText(f"Import abgeschlossen: {imported_count} importiert, {skipped_count} übersprungen/fehlgeschlagen.")
        QMessageBox.information(self, "Templates importiert", 
                                f"{imported_count} Templates erfolgreich importiert.\n{skipped_count} Templates konnten nicht importiert werden (z.B. Fehler beim Kopieren, Schreibrechte, etc.).")
        self.reload_templates_data_from_disk() # Templates-Liste in der App aktualisieren


    # NEU: Methode zum Sichern aller Templates im Benutzerverzeichnis
    @Slot()
    def backup_user_templates(self):
        if self.state["is_processing"]:
            QMessageBox.warning(self, "Verarbeitung läuft", "Bitte warten Sie, bis die aktuelle Verarbeitung abgeschlossen ist.")
            return

        if not os.path.exists(USER_TEMPLATES_PATH) or len([f for f in os.listdir(USER_TEMPLATES_PATH) if os.path.isfile(os.path.join(USER_TEMPLATES_PATH, f))]) == 0:
            QMessageBox.information(self, "Sicherung", "Keine Benutzer-Templates zum Sichern vorhanden.")
            return

        dest_dir = QFileDialog.getExistingDirectory(self, "Ordner zum Sichern der Templates auswählen")
        if not dest_dir:
            return

        backed_up_count = 0
        skipped_count = 0

        for filename in os.listdir(USER_TEMPLATES_PATH):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff')):
                src_path = os.path.join(USER_TEMPLATES_PATH, filename)
                dest_path = os.path.join(dest_dir, filename)
                try:
                    shutil.copy2(src_path, dest_path) 
                    backed_up_count += 1
                except Exception as e:
                    print(f"WARNUNG: Fehler beim Sichern von {filename}: {e}")
                    skipped_count += 1
        
        self.status_label.setText(f"Sicherung abgeschlossen: {backed_up_count} gesichert, {skipped_count} übersprungen/fehlgeschlagen.")
        QMessageBox.information(self, "Templates gesichert", 
                                f"{backed_up_count} Templates erfolgreich gesichert im Ordner:\n'{dest_dir}'\n{skipped_count} Templates konnten nicht gesichert werden.")
        self.update_ui() # UI aktualisieren, falls sich Button-Zustände ändern

    # NEU: Methode zum Löschen aller Templates im Benutzerverzeichnis
    @Slot()
    def clear_user_templates_data(self):
        if self.state["is_processing"]:
            QMessageBox.warning(self, "Verarbeitung läuft", "Bitte warten Sie, bis die aktuelle Verarbeitung abgeschlossen ist.")
            return

        # Zähle die Dateien im Ordner (ohne Unterordner, nur für die Anzeige)
        num_templates = len([f for f in os.listdir(USER_TEMPLATES_PATH) if os.path.isfile(os.path.join(USER_TEMPLATES_PATH, f))]) \
                        if os.path.exists(USER_TEMPLATES_PATH) else 0

        if num_templates == 0:
            QMessageBox.information(self, "Templates löschen", "Keine Benutzer-Templates zum Löschen gefunden.")
            return

        reply = QMessageBox.question(self, 'Templates löschen', 
                                     f"Möchten Sie WIRKLICH ALLE {num_templates} Templates im Ordner '{USER_TEMPLATES_PATH}' löschen?\n\nDIESE AKTION KANN NICHT RÜCKGÄNGIG GEMACHT WERDEN!",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.exists(USER_TEMPLATES_PATH):
                    shutil.rmtree(USER_TEMPLATES_PATH)
                    os.makedirs(USER_TEMPLATES_PATH) # Ordner neu erstellen, damit er existiert
                    print(f"DEBUG: Alle Benutzer-Templates in '{USER_TEMPLATES_PATH}' gelöscht.")
                    self.status_label.setText("Alle Benutzer-Templates gelöscht.")
                else:
                    self.status_label.setText("Keine Benutzer-Templates zum Löschen gefunden (Ordner existiert nicht).")
                
                self.reload_templates_data_from_disk() # Templates-Liste in der App aktualisieren
                QMessageBox.information(self, "Templates gelöscht", "Alle Benutzer-Templates erfolgreich gelöscht.")
            except Exception as e:
                QMessageBox.critical(self, "Fehler beim Löschen", f"Ein Fehler ist aufgetreten:\n{e}")
        self.update_ui()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DarkMarkApp()
    window.show()
    sys.exit(app.exec())
