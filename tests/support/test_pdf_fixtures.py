"""Readable PDF fixtures stored only under temporary test workspaces."""
from io import BytesIO
from pypdf import PdfWriter
from types import SimpleNamespace
from unittest.mock import patch

def pdf_upload():
    writer=PdfWriter();writer.add_blank_page(width=595,height=842)
    output=BytesIO();writer.write(output)
    return SimpleNamespace(name='test-borrow.pdf',getvalue=lambda:output.getvalue())

def install_pdf_fixture(test,path):
    from borrow_requests import save_document
    root_patch=patch('borrow_requests.PROJECT_DIR',path.parent);root_patch.start()
    test.addCleanup(root_patch.stop)
    return save_document(pdf_upload())
