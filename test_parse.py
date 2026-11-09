import os, io, re, uuid
from docx import Document
from PIL import Image

doc_path = r'C:/Users/Quach Nhi/.gemini/antigravity/brain/acbf1752-7288-4d7e-97ce-085a16d43afc/.user_uploaded/media_1793680626950_52d1a4d6.docx'
doc = Document(doc_path)
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
VML_NS = 'urn:schemas-microsoft-com:vml'

def extract_vml_image(imagedata_elem, doc):
    rId = imagedata_elem.get(f'{{{R_NS}}}id')
    if not rId or rId not in doc.part.related_parts:
        return None
    part = doc.part.related_parts[rId]
    data = part.blob
    fname = f'math_{uuid.uuid4().hex[:10]}.png'
    fpath = os.path.join(UPLOAD_DIR, fname)
    try:
        img = Image.open(io.BytesIO(data))
        img.save(fpath, 'PNG')
        return f'/static/uploads/{fname}'
    except Exception as e:
        return None

def parse_para(p):
    parts = []
    for child in p._p:
        tag = child.tag.split('}')[-1]
        if tag == 'r':
            for t in child.findall(f'{{{W_NS}}}t'):
                if t.text: parts.append(t.text)
            for imgdata in child.iter(f'{{{VML_NS}}}imagedata'):
                url = extract_vml_image(imgdata, doc)
                if url:
                    parts.append(f'<img src="{url}" class="inline-math-img" />')
    return ''.join(parts)

for i in [7, 8, 9, 10, 11]:
    print(f'Para {i}:', parse_para(doc.paragraphs[i]))
