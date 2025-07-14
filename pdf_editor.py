# --- START OF FILE pdf_editor.py ---
import os
import fitz # PyMuPDF
import cv2
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QLabel, QMessageBox
from PySide6.QtCore import Qt, Signal, QPoint, QRect, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QMouseEvent, QKeyEvent

class EditablePdfLabel(QLabel):
    """
    Ein QLabel, das interaktive Rechteckauswahlen auf einem angezeigten PDF-Bild ermöglicht.
    """
    selection_made = Signal(list)
    edit_mode_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(False)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        self._editing_mode_active = False
        self._start_point_relative_to_image = QPoint()
        self._current_selection_rect_relative_to_image = QRect()
        self._all_selection_rects_relative_to_image = []

        self.rubber_band_fill_color = QColor(255, 0, 0, 80)
        self.rubber_band_border_color = QColor(255, 0, 0)

        self._current_display_pixmap = None
        self._current_pixmap_display_rect = QRect()

    def setPixmap(self, pixmap: QPixmap):
        """Überschreibt setPixmap, um den Anzeigebereich des Pixmaps zu aktualisieren."""
        super().setPixmap(pixmap)
        self._current_display_pixmap = pixmap
        # WICHTIG: Hier muss der _current_pixmap_display_rect aktualisiert werden,
        # da die Größe des Pixmaps und/oder des Labels sich geändert haben könnte.
        self._current_pixmap_display_rect = self._calculate_pixmap_display_rect()
        self.update()

    def _calculate_pixmap_display_rect(self) -> QRect:
        """
        Berechnet das Rechteck des tatsächlich angezeigten Pixmaps innerhalb des Labels,
        unter Berücksichtigung von KeepAspectRatio und Zentrierung.
        """
        if not self._current_display_pixmap or self.size().isEmpty():
            return QRect()

        pixmap_size = self._current_display_pixmap.size()
        label_rect = self.contentsRect()

        if pixmap_size.isEmpty() or label_rect.isEmpty():
            return QRect()

        pixmap_aspect_ratio = pixmap_size.width() / pixmap_size.height()
        label_aspect_ratio = label_rect.width() / label_rect.height()

        display_width = 0
        display_height = 0

        if pixmap_aspect_ratio > label_aspect_ratio:
            # Pixmap ist im Verhältnis breiter als das Label -> Breite füllt aus, Höhe wird skaliert
            display_width = label_rect.width()
            display_height = int(display_width / pixmap_aspect_ratio)
        else:
            # Pixmap ist im Verhältnis höher als das Label -> Höhe füllt aus, Breite wird skaliert
            display_height = label_rect.height()
            display_width = int(display_height * pixmap_aspect_ratio)

        # Zentrieren des angezeigten Bildes innerhalb des Labels
        offset_x = label_rect.x() + (label_rect.width() - display_width) // 2
        offset_y = label_rect.y() + (label_rect.height() - display_height) // 2

        return QRect(offset_x, offset_y, display_width, display_height)

    def set_editing_mode(self, active: bool):
        """
        Aktiviert oder deaktiviert den Bearbeitungsmodus für das Label.
        """
        if self._editing_mode_active == active:
            return

        self._editing_mode_active = active
        if active:
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.grabKeyboard()
            self.clear_selections()
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.releaseKeyboard()
            self.clear_selections()

        self.edit_mode_changed.emit(active)
        self.update()

    def is_editing_mode(self) -> bool:
        """Gibt zurück, ob der Bearbeitungsmodus aktiv ist."""
        return self._editing_mode_active

    def clear_selections(self):
        """Löscht alle aktuellen und bestätigten Auswahlrechtecke."""
        self._current_selection_rect_relative_to_image = QRect()
        self._all_selection_rects_relative_to_image = []
        self._start_point_relative_to_image = QPoint()
        self.update()

    def get_selections_in_label_coords(self) -> list[QRect]:
        """
        Gibt die Liste der bestätigten Auswahlrechtecke in den
        Pixelkoordinaten des *skalierten QPixmap* zurück, das im Label angezeigt wird.
        """
        return self._all_selection_rects_relative_to_image


    def mousePressEvent(self, event: QMouseEvent):
        if self._editing_mode_active and event.button() == Qt.MouseButton.LeftButton:
            if self._current_pixmap_display_rect.contains(event.pos()):
                local_pos = event.pos() - self._current_pixmap_display_rect.topLeft()
                self._start_point_relative_to_image = local_pos
                self._current_selection_rect_relative_to_image = QRect(local_pos, local_pos)
                self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._editing_mode_active and event.buttons() == Qt.MouseButton.LeftButton and not self._start_point_relative_to_image.isNull():
            local_pos = event.pos() - self._current_pixmap_display_rect.topLeft()
            self._current_selection_rect_relative_to_image = QRect(self._start_point_relative_to_image, local_pos).normalized()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._editing_mode_active and event.button() == Qt.MouseButton.LeftButton and not self._start_point_relative_to_image.isNull():
            local_pos = event.pos() - self._current_pixmap_display_rect.topLeft()
            final_rect_relative_to_image = QRect(self._start_point_relative_to_image, local_pos).normalized()

            pixmap_actual_size = self._current_display_pixmap.size() if self._current_display_pixmap else QSize(0,0)
            img_rect_bounds = QRect(QPoint(0,0), pixmap_actual_size)
            final_rect_relative_to_image = final_rect_relative_to_image.intersected(img_rect_bounds)

            if final_rect_relative_to_image.width() > 5 and final_rect_relative_to_image.height() > 5:
                if not final_rect_relative_to_image.isEmpty():
                    self._all_selection_rects_relative_to_image.append(final_rect_relative_to_image)
                    self.selection_made.emit(self._all_selection_rects_relative_to_image)

            self._current_selection_rect_relative_to_image = QRect()
            self._start_point_relative_to_image = QPoint()
            self.update()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if self._editing_mode_active and event.key() == Qt.Key.Key_Backspace:
            if self._all_selection_rects_relative_to_image:
                self._all_selection_rects_relative_to_image.pop()
                self.update()
                self.selection_made.emit(self._all_selection_rects_relative_to_image)
        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)

        if self._editing_mode_active:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Übersetze den Painter-Ursprung auf den Startpunkt des angezeigten Bildes
            painter.translate(self._current_pixmap_display_rect.topLeft())

            pen = QPen(self.rubber_band_border_color)
            pen.setWidth(2)
            painter.setPen(pen)

            painter.setBrush(self.rubber_band_fill_color)

            for rect in self._all_selection_rects_relative_to_image:
                painter.drawRect(rect)

            if not self._current_selection_rect_relative_to_image.isNull():
                painter.drawRect(self._current_selection_rect_relative_to_image)

            painter.end()


def extract_and_save_regions(
    fitz_doc: fitz.Document,
    page_num: int,
    selections_px_relative_to_display: list[QRect], # Koordinaten relativ zum im QLabel angezeigten Pixmap
    displayed_qpixmap_size: QSize,                # Größe des im QLabel angezeigten Pixmaps
    full_render_qpixmap_size: QSize,              # NEU: Größe des Pixmaps, wenn es mit RENDER_DPI ohne Fit-to-Label gerendert wurde
    template_dir_path: str,
    render_dpi: int
) -> int:
    """
    Extrahiert ausgewählte Regionen aus einer PDF-Seite und speichert sie als PNG-Templates.

    Args:
        fitz_doc: Das PyMuPDF-Dokumentobjekt, aus dem extrahiert werden soll.
        page_num: Die 0-basierte Seitennummer der aktuellen PDF-Seite.
        selections_px_relative_to_display: Eine Liste von QRect-Objekten, die die Auswahlen
                                         in den Pixelkoordinaten des *skalierten QPixmap* darstellen,
                                         das im QLabel angezeigt wird.
        displayed_qpixmap_size: Die tatsächliche QSize des QPixmap, das gerade im QLabel
                                angezeigt wird (nach der Skalierung für die Anzeige).
        full_render_qpixmap_size: Die Größe des Pixmaps, das direkt mit RENDER_DPI von PyMuPDF
                                  gerendert wurde (das "Goldstandard"-Bild für Templates).
        template_dir_path: Das Verzeichnis, in dem die Templates gespeichert werden sollen.
        render_dpi: Die DPI, mit der die extrahierten Regionen gerendert werden sollen (z.B. 300).

    Returns:
        Die Anzahl der erfolgreich gespeicherten Templates.
    """
    if not selections_px_relative_to_display:
        return 0

    saved_count = 0
    try:
        page = fitz_doc.load_page(page_num)

        # --- Schritt 1: Rendere die GESAMTE Seite mit RENDER_DPI ---
        # Dies ist genau das Bild, auf dem später die Matching-Operation stattfinden wird.
        mat_for_full_render = fitz.Matrix(render_dpi / 72, render_dpi / 72)
        full_page_pix = page.get_pixmap(matrix=mat_for_full_render, alpha=False)
        full_page_img_pil = Image.frombytes("RGB", [full_page_pix.width, full_page_pix.height], full_page_pix.samples)
        # Konvertiere zu OpenCV-Graustufenbild für konsistentes Template-Format
        full_page_cv_img_gray = np.array(full_page_img_pil.convert('L')) # Convert to Grayscale for template matching


        # --- Schritt 2: Skaliere die Benutzer-Auswahlkoordinaten vom angezeigten Bild
        #             auf die Pixelkoordinaten des Voll-Render-Bildes (full_page_cv_img_gray) ---
        # Bestimme den Skalierungsfaktor, der auf das Bild angewendet wurde, um es anzuzeigen
        # Die Ratio zwischen dem "Full Render Pixmap" und dem "Angezeigten Pixmap".
        # Diese Ratio ist entscheidend für die Umrechnung.
        # Da KeepAspectRatio aktiv ist, sollten die Verhältnisse in X und Y gleich sein.
        # Wir nehmen die Breite als Referenz, vorausgesetzt sie ist nicht 0.
        if displayed_qpixmap_size.width() == 0 or full_render_qpixmap_size.width() == 0:
            raise ValueError("Ungültige Pixmap-Breite für Skalierung.")

        # Das displayed_qpixmap_size ist die Größe des Pixmap, das NACH scaled()
        # im QLabel liegt. full_render_qpixmap_size ist die Größe VOR scaled().
        # Daher ist der Skalierungsfaktor umgekehrt: wie viel kleiner ist das angezeigte Bild
        # im Vergleich zum voll gerenderten Bild.
        scale_from_display_to_full_render = full_render_qpixmap_size.width() / displayed_qpixmap_size.width()


        for i, sel_px_display_coords in enumerate(selections_px_relative_to_display):
            # Skaliere die Auswahlrechteck-Koordinaten auf die Dimensionen des Voll-Render-Bildes
            x1_full_render = int(sel_px_display_coords.x() * scale_from_display_to_full_render)
            y1_full_render = int(sel_px_display_coords.y() * scale_from_display_to_full_render)
            x2_full_render = int((sel_px_display_coords.x() + sel_px_display_coords.width()) * scale_from_display_to_full_render)
            y2_full_render = int((sel_px_display_coords.y() + sel_px_display_coords.height()) * scale_from_display_to_full_render)

            # Sicherstellen, dass die Koordinaten innerhalb der Grenzen des Voll-Render-Bildes liegen
            # und dass x2 > x1 und y2 > y1
            x1_full_render = max(0, x1_full_render)
            y1_full_render = max(0, y1_full_render)
            x2_full_render = min(full_page_cv_img_gray.shape[1], x2_full_render)
            y2_full_render = min(full_page_cv_img_gray.shape[0], y2_full_render)

            # Schneide das Template direkt aus dem Voll-Render-Bild aus
            # Beachte: NumPy-Slicing ist [row_start:row_end, col_start:col_end] -> [y1:y2, x1:x2]
            cropped_template_cv = full_page_cv_img_gray[y1_full_render:y2_full_render, x1_full_render:x2_full_render]

            if cropped_template_cv.size == 0 or cropped_template_cv.shape[0] == 0 or cropped_template_cv.shape[1] == 0:
                print(f"WARNUNG: Leeres oder zu kleines Template aus Region {i+1} auf Seite {page_num+1} generiert. Überspringe.")
                continue

            # Konvertiere das zugeschnittene OpenCV-Bild zurück zu PIL Image für das Speichern
            img_to_save = Image.fromarray(cropped_template_cv)

            output_filename = f"template_page_{page_num + 1:04d}_region_{i + 1:02d}.png"
            output_path = os.path.join(template_dir_path, output_filename)

            os.makedirs(template_dir_path, exist_ok=True)

            img_to_save.save(output_path)
            saved_count += 1
            print(f"DEBUG: Saved template: {output_path}")

    except Exception as e:
        print(f"ERROR: Failed to extract and save regions: {e}")
        QMessageBox.critical(None, "Fehler beim Speichern der Templates", f"Ein Fehler ist aufgetreten: {e}")
    return saved_count

# --- END OF FILE pdf_editor.py ---