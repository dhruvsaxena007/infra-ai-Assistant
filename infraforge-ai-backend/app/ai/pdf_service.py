from pypdf import PdfReader


def extract_text_from_pdf(pdf_path: str):
    """
    Extract text from uploaded PDF.
    """

    try:

        reader = PdfReader(pdf_path)

        text = ""

        for page in reader.pages:

            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

        if not text.strip():

            return {
                "success": False,
                "message": "No readable text found in PDF"
            }

        return {
            "success": True,
            "text": text
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }