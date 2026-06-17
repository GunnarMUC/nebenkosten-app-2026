import os
import subprocess
import pytesseract
from PIL import Image
from flask import current_app

class OCRService:
    """Service for OCR text extraction from images and PDFs."""

    def __init__(self):
        pass

    def extract_text(self, file_path, max_pages=10):
        """Extract text from an image or PDF file.
        
        Args:
            file_path: Path to the file
            max_pages: Maximum pages to process (safety limit for large PDFs)
        
        Returns:
            dict with 'text', 'pages', 'success', 'error'
        """
        try:
            ext = os.path.splitext(file_path)[1].lower()
            
            if ext in ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif', '.webp']:
                return self._extract_from_image(file_path)
            elif ext == '.pdf':
                return self._extract_from_pdf(file_path, max_pages=max_pages)
            else:
                return {'text': '', 'pages': 0, 'success': False, 'error': f'Nicht unterstuetztes Format: {ext}'}
        except Exception as e:
            current_app.logger.error(f"OCR extraction failed: {e}")
            return {'text': '', 'pages': 0, 'success': False, 'error': str(e)}

    def _extract_from_image(self, image_path):
        """Extract text from image using Tesseract OCR."""
        try:
            image = Image.open(image_path)
            # Use German language model
            text = pytesseract.image_to_string(image, lang='deu')
            return {
                'text': text,
                'pages': 1,
                'success': True,
                'error': None
            }
        except Exception as e:
            return {'text': '', 'pages': 0, 'success': False, 'error': f'Bild-OCR fehlgeschlagen: {e}'}

    def _extract_from_pdf(self, pdf_path, max_pages=10):
        """Extract text from PDF using multiple methods with page limit."""
        
        # Method 1: Try PyMuPDF first (fastest for text-based PDFs)
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            pages_to_process = min(total_pages, max_pages)
            all_text = []
            
            for page_num in range(pages_to_process):
                page = doc[page_num]
                text = page.get_text()
                all_text.append(f"--- Seite {page_num+1} ---\n{text}")
            
            doc.close()
            full_text = "\n\n".join(all_text)
            
            if full_text.strip():
                truncated_msg = f" ({pages_to_process}/{total_pages} Seiten)" if total_pages > max_pages else ""
                return {
                    'text': full_text,
                    'pages': pages_to_process,
                    'success': True,
                    'error': None,
                    'truncated': total_pages > max_pages,
                    'total_pages': total_pages
                }
        except ImportError:
            pass
        except Exception as e:
            current_app.logger.warning(f"PyMuPDF failed: {e}")
        
        # Method 2: Try pdftotext (poppler-utils) - fast fallback
        try:
            result = subprocess.run(
                ['pdftotext', pdf_path, '-'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                text = result.stdout[:50000]  # Limit text length
                return {
                    'text': text,
                    'pages': 1,
                    'success': True,
                    'error': None
                }
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            pass
        
        # Method 3: pdf2image + Tesseract (slowest, for scanned PDFs)
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=max_pages)
            all_text = []
            for i, image in enumerate(images):
                text = pytesseract.image_to_string(image, lang='deu')
                all_text.append(f"--- Seite {i+1} ---\n{text}")
            
            return {
                'text': "\n\n".join(all_text),
                'pages': len(images),
                'success': True,
                'error': None
            }
        except ImportError:
            pass
        except Exception as e:
            current_app.logger.warning(f"pdf2image failed: {e}")
        
        # All methods failed
        return {
            'text': '',
            'pages': 0,
            'success': False,
            'error': 'PDF konnte nicht verarbeitet. Installieren Sie: pip install PyMuPDF pdf2image'
        }
