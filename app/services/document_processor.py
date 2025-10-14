import os
import tempfile
from typing import Tuple, Optional
from pathlib import Path
import pytesseract
from PIL import Image
import pdfplumber
from pdf2image import convert_from_path
from fastapi import UploadFile

# Configure tesseract path (Windows users may need to set this)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


class DocumentProcessor:
    """
    Process uploaded documents (PDF, images) and extract text using OCR
    """
    
    SUPPORTED_IMAGE_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}
    SUPPORTED_PDF_FORMAT = '.pdf'
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
    
    async def process_upload(self, file: UploadFile) -> Tuple[str, dict]:
        """
        Process uploaded file and extract text
        
        Returns:
            Tuple of (extracted_text, metadata)
        """
        # Validate file
        file_ext = Path(file.filename).suffix.lower()
        
        if file_ext not in self.SUPPORTED_IMAGE_FORMATS and file_ext != self.SUPPORTED_PDF_FORMAT:
            raise ValueError(
                f"Unsupported file format: {file_ext}. "
                f"Supported formats: {', '.join(self.SUPPORTED_IMAGE_FORMATS | {self.SUPPORTED_PDF_FORMAT})}"
            )
        
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(f"File too large. Maximum size: {self.MAX_FILE_SIZE / (1024*1024):.1f} MB")
        
        # Save to temporary file
        temp_file_path = os.path.join(self.temp_dir, f"temp_{file.filename}")
        
        try:
            with open(temp_file_path, 'wb') as f:
                f.write(content)
            
            # Process based on file type
            if file_ext == self.SUPPORTED_PDF_FORMAT:
                extracted_text, metadata = self._process_pdf(temp_file_path)
            else:
                extracted_text, metadata = self._process_image(temp_file_path)
            
            # Add file info to metadata
            metadata.update({
                'original_filename': file.filename,
                'file_size_bytes': file_size,
                'file_type': file_ext
            })
            
            return extracted_text, metadata
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    
    def _process_image(self, image_path: str) -> Tuple[str, dict]:
        """
        Extract text from image using OCR
        """
        try:
            # Open image
            image = Image.open(image_path)
            
            # Get image metadata
            width, height = image.size
            
            # Perform OCR
            text = pytesseract.image_to_string(image)
            
            # Get OCR confidence data
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            confidences = [int(conf) for conf in data['conf'] if conf != '-1']
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            metadata = {
                'processing_method': 'OCR (Tesseract)',
                'image_width': width,
                'image_height': height,
                'ocr_confidence': round(avg_confidence, 2),
                'character_count': len(text),
                'word_count': len(text.split())
            }
            
            return text.strip(), metadata
            
        except Exception as e:
            raise Exception(f"Error processing image: {str(e)}")
    
    def _process_pdf(self, pdf_path: str) -> Tuple[str, dict]:
        """
        Extract text from PDF using pdfplumber and OCR fallback
        """
        try:
            extracted_text = []
            total_pages = 0
            pages_with_text = 0
            pages_ocr_needed = 0
            
            # First try: Extract text directly from PDF
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text()
                    
                    if text and len(text.strip()) > 50:
                        # Page has extractable text
                        extracted_text.append(text)
                        pages_with_text += 1
                    else:
                        # Page needs OCR (likely scanned/image-based)
                        pages_ocr_needed += 1
            
            # If most pages need OCR, convert PDF to images and OCR
            if pages_ocr_needed > total_pages / 2:
                print(f"PDF appears to be scanned. Running OCR on {pages_ocr_needed} pages...")
                ocr_text = self._ocr_pdf(pdf_path)
                if ocr_text:
                    extracted_text = [ocr_text]
            
            combined_text = "\n\n".join(extracted_text)
            
            metadata = {
                'processing_method': 'PDF Text Extraction + OCR',
                'total_pages': total_pages,
                'pages_with_text': pages_with_text,
                'pages_ocr_needed': pages_ocr_needed,
                'character_count': len(combined_text),
                'word_count': len(combined_text.split())
            }
            
            return combined_text.strip(), metadata
            
        except Exception as e:
            raise Exception(f"Error processing PDF: {str(e)}")
    
    def _ocr_pdf(self, pdf_path: str) -> str:
        """
        Convert PDF pages to images and perform OCR
        """
        try:
            # Convert PDF to images
            images = convert_from_path(pdf_path)
            
            extracted_texts = []
            for i, image in enumerate(images, 1):
                print(f"OCR processing page {i}/{len(images)}...")
                text = pytesseract.image_to_string(image)
                extracted_texts.append(text)
            
            return "\n\n".join(extracted_texts)
            
        except Exception as e:
            print(f"Error during PDF OCR: {str(e)}")
            return ""


# Singleton instance
document_processor = DocumentProcessor()