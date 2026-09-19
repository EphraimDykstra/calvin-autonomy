"""Deterministic PDF and DOCX rendering for engineering deliverables."""
from __future__ import annotations
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
from .identity import deliverable_identity

def _paragraph(story, text, style, Paragraph):
    for line in str(text or '').split('\n'):
        if line.strip(): story.append(Paragraph(escape(line.strip()),style))

def _required_figure_roles(rendering:dict)->list[str]:
    """Figure roles the course profile requires the deliverable to carry."""
    value=rendering.get('required_figures',[])
    if value in (None,[]): return []
    if not isinstance(value,list): raise ValueError('rendering.required_figures must be a list of role names')
    roles=[]
    for item in value:
        if not isinstance(item,str) or not item.strip(): raise ValueError('rendering.required_figures entries must be non-empty strings')
        roles.append(item.strip().casefold())
    return roles

def _declared_figure_roles(solution:dict)->set[str]:
    """Roles declared by figures anywhere in the solution, body or appendix."""
    roles=set()
    groups=[solution.get('sections',[]),solution.get('appendices',[])]
    for group in groups:
        if not isinstance(group,list): continue
        for section in group:
            if not isinstance(section,dict): continue
            figures=section.get('figures',[])
            if not isinstance(figures,list): continue
            for item in figures:
                if not isinstance(item,dict): continue
                role=item.get('role')
                if isinstance(role,str) and role.strip(): roles.add(role.strip().casefold())
    return roles

def _check_required_figures(solution:dict,rendering:dict)->None:
    """Refuse to render when a figure the course requires is absent.

    A required figure is declared by role rather than by caption text so that
    wording changes cannot silently satisfy or break the requirement.  The
    check accepts the figure in an appendix as well as the body, because course
    conventions differ on where an apparatus schematic belongs.
    """
    required=_required_figure_roles(rendering)
    if not required: return
    missing=sorted(set(required)-_declared_figure_roles(solution))
    if missing:
        raise ValueError('solution is missing required figure role(s): '+', '.join(missing))

def _body_page_budget(rendering:dict)->int | None:
    """Maximum number of numbered body pages the course profile allows."""
    value=rendering.get('max_body_pages')
    if value is None: return None
    if isinstance(value,bool) or not isinstance(value,int) or value < 1:
        raise ValueError('rendering.max_body_pages must be a positive integer')
    return value

# Both renderers lay out on US Letter, in points (1/72 inch).
PAGE_POINTS=(8.5*72,11*72)

def _figure_frame_points(rendering:dict)->tuple[float,float]:
    """Largest box either renderer will draw a figure in, from the profile's margins.

    The width is the text column, so a full-width figure lines up with the text
    and never crosses the margin the profile declared.  The height is half the
    text block, so a figure at full height still leaves room on its page for its
    caption and the text that refers to it; at the default 1in margins that is
    4.5in.
    """
    margin=float(rendering.get('margin_inches',1))*72
    width=PAGE_POINTS[0]-2*margin; height=(PAGE_POINTS[1]-2*margin)/2
    if not (math.isfinite(width) and math.isfinite(height)) or width<=0 or height<=0:
        raise ValueError('rendering.margin_inches leaves no printable area for figures')
    return width,height

def _figure_box_points(item:dict,frame:tuple[float,float])->tuple[float,float] | None:
    """A figure's declared size in points, or None when it declares none.

    ``width`` and ``height`` are read as a bounding box that the image is fitted
    inside with its aspect ratio preserved, so declaring one dimension is enough
    and declaring both can never distort the figure.  The unit is points because
    the PDF page is measured in them and a DOCX length converts exactly at /72,
    which lets one declared number mean the same size in both renderers.

    A box larger than the printable area is refused rather than quietly reduced:
    silently discarding a declared size is the defect this function exists to
    remove, and clamping would be the same defect with a smaller blast radius.

    A plot from ``plots.render_line_plot`` records the size it was drawn for;
    ``_figure_points`` holds a declared box to that size.
    """
    if 'width' not in item and 'height' not in item: return None
    box=[]
    for limit,name in zip(frame,('width','height')):
        value=item.get(name)
        if value is None:
            box.append(limit); continue
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            raise ValueError(f'figure {name} must be a positive number of points')
        if value>limit:
            raise ValueError(f'figure {name} of {float(value):g}pt exceeds the {limit:g}pt printable area')
        box.append(float(value))
    return box[0],box[1]

# pHYs holds whole pixels per metre, so a plot declared at exactly its own
# target measures a few thousandths of a point off it.  Equality would refuse
# the one declaration the plot contract asks for.  1% is far below a legibility
# change: a 6.3pt title stays above 6.2pt.
PLOT_SIZE_TOLERANCE=0.01

def _plot_marker_points(image)->tuple[float,float] | None:
    """The physical size a project plot was drawn for, or None for any other image.

    Most image tools write pHYs, so a resolution alone says nothing about the
    size an image was designed to be read at.  Only a plot carrying the key that
    ``render_line_plot`` writes is trusted; every other image, including one
    with no pHYs at all, is fitted exactly as before rather than guessed at.
    """
    from .plots import PLOT_MARKER_KEY
    dpi=image.info.get('dpi')
    if PLOT_MARKER_KEY not in image.info or not dpi: return None
    try: x,y=float(dpi[0]),float(dpi[1])
    except (TypeError,ValueError,IndexError): return None
    if not (math.isfinite(x) and math.isfinite(y) and x>0 and y>0): return None
    return image.size[0]/x*72,image.size[1]/y*72

def _figure_points(path:Path,item:dict,frame:tuple[float,float])->tuple[float,float]:
    """The size, in points, at which both renderers draw this figure.

    One rule for both renderers, so they cannot drift apart:

    * a marked plot with no declared size is drawn at the size it was made for;
    * a marked plot whose declared box fits it to a materially different size
      is refused, because that rescales its text away from the legibility
      floor it was drawn to meet;
    * an unmarked image is fitted into the frame, never enlarged past one point
      per pixel, since upscaling a raster adds no information and softens it.

    A marked plot larger than the printable area is refused with the width to
    render it at, rather than shrunk to fit, which would be the same defect.
    """
    from PIL import Image as PillowImage
    box=_figure_box_points(item,frame)
    with PillowImage.open(path) as image:
        pixel_width,pixel_height=image.size
        marked=_plot_marker_points(image)
    if pixel_width<=0 or pixel_height<=0: raise ValueError('figure dimensions must be positive')
    frame_width,frame_height=frame
    if marked is not None:
        # Compared by width: each axis of the canvas is rounded to whole pixels
        # separately, so the two axes can disagree by a fraction of a pixel.
        marked_scale=marked[0]/pixel_width
        if box is None:
            fits=min(frame_width/marked[0],frame_height/marked[1])
            if fits<1-PLOT_SIZE_TOLERANCE:
                raise ValueError(
                    f'plot {path.name} was rendered at {marked[0]:.0f}x{marked[1]:.0f}pt, larger than the '
                    f'{frame_width:g}x{frame_height:g}pt printable area; render it at width '
                    f'{marked[0]*fits:.0f} or less so its text keeps the size it was drawn for'
                )
            # Drawn at the marked size itself; within the tolerance, trimmed to the frame.
            trim=min(fits,1.0)
            return marked[0]*trim,marked[1]*trim
        else:
            scale=min(box[0]/pixel_width,box[1]/pixel_height)
            if abs(scale/marked_scale-1)>PLOT_SIZE_TOLERANCE:
                raise ValueError(
                    f'figure {path.name} declares a size that draws it at {pixel_width*scale:.0f}pt wide, but '
                    f'the plot was rendered for {marked[0]:.0f}pt; declare width {marked[0]:.0f} or render '
                    f'the plot at the width the figure needs, or its text will not print at the size it was drawn for'
                )
    elif box is None:
        scale=min(frame_width/pixel_width,frame_height/pixel_height,1)
    else:
        scale=min(box[0]/pixel_width,box[1]/pixel_height)
    return pixel_width*scale,pixel_height*scale

def _safe_figure(run_root:Path,value:Any)->Path:
    if not isinstance(value,str) or not value.strip(): raise ValueError('figure path must be a non-empty string')
    raw=Path(value)
    if raw.is_absolute() or '..' in raw.parts: raise ValueError('figure path must be relative to the assignment run')
    path=run_root/raw
    if path.is_symlink() or not path.is_file(): raise ValueError('figure must be a regular file inside the assignment run')
    try: path.resolve().relative_to(run_root.resolve())
    except ValueError as exc: raise ValueError('figure must remain inside the assignment run') from exc
    return path


def _normalize_docx_package(path: Path) -> None:
    """Rewrite a DOCX with stable member order, timestamps, and compression."""
    temporary = path.with_name(f".{path.name}.deterministic")
    with ZipFile(path, "r") as source:
        members = [(info.filename, source.read(info.filename)) for info in source.infolist()]
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as target:
            for name, data in sorted(members):
                info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.create_system = 0
                info.external_attr = 0
                target.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def render_text_docx(
    solution: dict,
    output: Path,
    *,
    identity: dict | None = None,
    style_profile: dict | None = None,
) -> Path:
    """Render the solution schema as an editable, deterministic DOCX file."""
    try:
        from docx import Document
        from docx.enum.section import WD_SECTION
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt
        from PIL import Image as PillowImage
    except ImportError as exc:
        raise RuntimeError("python-docx and pillow are required to render DOCX") from exc
    if not isinstance(solution, dict):
        raise ValueError("solution must be an object")

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    run_root = output.parent.parent
    rendering = style_profile.get("rendering", {}) if isinstance(style_profile, dict) else {}
    body_size = float(rendering.get("body_font_size", 10))
    line_spacing = float(rendering.get("line_spacing", 1.2))
    margin = float(rendering.get("margin_inches", 1))
    title_page = bool(rendering.get("title_page", True))
    report = solution.get("document_type") == "technical_report"
    memo = solution.get("document_type") == "memo"
    # DOCX has no fixed pagination, so a page budget cannot be checked here;
    # the required-figure rule is independent of pagination and does apply.
    _check_required_figures(solution, rendering)
    frame = _figure_frame_points(rendering)
    metadata = deliverable_identity(identity)
    title = str(solution.get("title", "Engineering Assignment"))

    document = Document()
    normal = document.styles["Normal"]
    normal.font.size = Pt(body_size)
    normal.paragraph_format.line_spacing = line_spacing
    caption_style = document.styles["Caption"]
    caption_style.font.size = Pt(min(body_size, 9))
    caption_style.paragraph_format.space_after = Pt(8)
    for section in document.sections:
        section.top_margin = Inches(margin)
        section.bottom_margin = Inches(margin)
        section.left_margin = Inches(margin)
        section.right_margin = Inches(margin)

    properties = document.core_properties
    properties.title = title
    properties.author = metadata["display_name"]
    properties.last_modified_by = metadata["display_name"]
    properties.created = datetime(2000, 1, 1, tzinfo=timezone.utc)
    properties.modified = datetime(2000, 1, 1, tzinfo=timezone.utc)
    properties.revision = 1

    def add_text(value: Any, *, style: str | None = None, centered: bool = False) -> None:
        for line in str(value or "").split("\n"):
            if not line.strip():
                continue
            paragraph = document.add_paragraph(line.strip(), style=style)
            if centered:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def add_page_number(section, start: int = 1) -> None:
        section.footer.is_linked_to_previous = False
        paragraph = section.footer.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run()
        begin = OxmlElement("w:fldChar")
        begin.set(qn("w:fldCharType"), "begin")
        instruction = OxmlElement("w:instrText")
        instruction.set(qn("xml:space"), "preserve")
        instruction.text = " PAGE "
        separate = OxmlElement("w:fldChar")
        separate.set(qn("w:fldCharType"), "separate")
        text = OxmlElement("w:t")
        text.text = str(start)
        end = OxmlElement("w:fldChar")
        end.set(qn("w:fldCharType"), "end")
        for element in (begin, instruction, separate, text, end):
            run._r.append(element)
        page_number = OxmlElement("w:pgNumType")
        page_number.set(qn("w:start"), str(start))
        section._sectPr.append(page_number)

    if memo:
        for label, value in memo_header_rows(solution, metadata["display_name"]):
            line = document.add_paragraph()
            line.add_run(f"{label}:").bold = True
            line.add_run(f"\t{value}")
        # A rule under the header separates it from the body, as a memo does.
        rule = document.add_paragraph()
        borders = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        for attribute, value in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "auto")):
            bottom.set(qn(attribute), value)
        borders.append(bottom)
        rule._p.get_or_add_pPr().append(borders)
        body_section = document.sections[0]
    elif report and title_page:
        title_paragraph = document.add_paragraph(title, style="Title")
        title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        details = solution.get("metadata", {}) if isinstance(solution.get("metadata", {}), dict) else {}
        for value in (
            details.get("course"),
            details.get("section"),
            metadata["display_name"],
            metadata["student_id"],
            details.get("date"),
        ):
            if value:
                add_text(value, centered=True)
        if rendering.get("abstract", False) and not solution.get("abstract"):
            raise ValueError("course profile requires an abstract")
        if solution.get("abstract"):
            document.add_heading("Abstract", level=2)
            add_text(solution["abstract"])
        body_section = document.add_section(WD_SECTION.NEW_PAGE)
        body_section.top_margin = Inches(margin)
        body_section.bottom_margin = Inches(margin)
        body_section.left_margin = Inches(margin)
        body_section.right_margin = Inches(margin)
    else:
        document.add_heading(title, level=0)
        body_section = document.sections[0]

    if rendering.get("number_body_pages", True):
        add_page_number(body_section)

    def add_section(section: dict, *, appendix: bool = False) -> None:
        heading = str(section.get("heading", "Appendix" if appendix else ""))
        if heading:
            document.add_heading(heading, level=2)
        add_text(section.get("body", ""))
        equations = section.get("equations", [])
        if isinstance(equations, list):
            for equation in equations:
                add_text(equation, centered=True)

        tables = section.get("tables", [])
        if isinstance(tables, list):
            for item in tables:
                if not isinstance(item, dict):
                    continue
                headers, rows = item.get("headers", []), item.get("rows", [])
                if not isinstance(headers, list) or not isinstance(rows, list) or not all(isinstance(row, list) for row in rows):
                    raise ValueError("table headers and rows must be lists")
                widths = [len(headers)] if headers else []
                widths.extend(len(row) for row in rows)
                if widths and (not widths[0] or any(width != widths[0] for width in widths)):
                    raise ValueError("table rows must have a consistent non-zero column count")
                caption = str(item.get("caption", "")).strip()
                if caption and rendering.get("table_captions_above", True):
                    document.add_paragraph(caption, style="Caption")
                if widths:
                    table = document.add_table(rows=len(rows) + (1 if headers else 0), cols=widths[0])
                    table.style = "Table Grid"
                    offset = 0
                    if headers:
                        for index, value in enumerate(headers):
                            table.cell(0, index).text = str(value)
                        offset = 1
                    for row_index, row in enumerate(rows, start=offset):
                        for column_index, value in enumerate(row):
                            table.cell(row_index, column_index).text = str(value)
                if caption and not rendering.get("table_captions_above", True):
                    document.add_paragraph(caption, style="Caption")

        figures = section.get("figures", [])
        if isinstance(figures, list):
            for item in figures:
                if not isinstance(item, dict):
                    continue
                path = _safe_figure(run_root, item.get("path"))
                width, height = _figure_points(path, item, frame)
                caption = str(item.get("caption", "")).strip()
                if caption and not rendering.get("figure_captions_below", True):
                    document.add_paragraph(caption, style="Caption")
                picture_paragraph = document.add_paragraph()
                picture_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                picture_paragraph.add_run().add_picture(str(path), width=Pt(width), height=Pt(height))
                if caption and rendering.get("figure_captions_below", True):
                    document.add_paragraph(caption, style="Caption")

    sections = solution.get("sections", [])
    if isinstance(sections, list):
        for section in sections:
            if isinstance(section, dict):
                add_section(section)
    appendices = solution.get("appendices", [])
    if isinstance(appendices, list) and appendices:
        document.add_page_break()
        for appendix in appendices:
            if isinstance(appendix, dict):
                add_section(appendix, appendix=True)

    document.save(output)
    _normalize_docx_package(output)
    return output

MEMO_FIELDS = (("to", "To"), ("from", "From"), ("cc", "CC"), ("date", "Date"), ("re", "Re"))


def memo_header_rows(solution: dict, display_name: str) -> list[tuple[str, str]]:
    """Return a header memo's To, From, CC, Date and Re lines, or refuse an incomplete one.

    "Technical memo" names two different documents at Calvin, and this is the
    header form: a To/From/CC/Date/Re block, then the body.  A document that
    declares itself a memo must carry that header, because without it the
    result looks finished and is the wrong document.  From defaults to the run
    identity, a placeholder unless the student supplied one; To has no default,
    since it is the instructor, which the host reads off the student's own
    assignment sheet.  The subject line falls back to the title.
    """
    header = solution.get("memo_header")
    if not isinstance(header, dict):
        raise ValueError("a memo needs a memo_header with to, date and re")
    values = {key: str(header.get(key) or "").strip() for key, _ in MEMO_FIELDS}
    if not values["from"]:
        values["from"] = str(display_name or "").strip()
    if not values["re"]:
        values["re"] = str(solution.get("title") or "").strip()
    missing = [label for key, label in MEMO_FIELDS if key != "cc" and not values[key]]
    if missing:
        raise ValueError("a memo header needs " + ", ".join(missing))
    return [(label, values[key]) for key, label in MEMO_FIELDS if values[key]]


def render_text_pdf(solution:dict, output:Path, *, identity:dict | None = None, style_profile:dict | None = None)->Path:
    """Render a worked problem or an opted-in course-style technical report."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Flowable,Image,PageBreak,Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
    except ImportError as e: raise RuntimeError('reportlab is required to render PDF') from e
    if not isinstance(solution,dict): raise ValueError('solution must be an object')
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True); run_root=output.parent.parent
    styles=getSampleStyleSheet(); story=[]
    rendering=style_profile.get('rendering',{}) if isinstance(style_profile,dict) else {}
    body_size=float(rendering.get('body_font_size',10)); line_spacing=float(rendering.get('line_spacing',1.2)); margin=float(rendering.get('margin_inches',1))*inch
    styles['BodyText'].fontSize=body_size; styles['BodyText'].leading=body_size*line_spacing
    caption=ParagraphStyle('Caption',parent=styles['BodyText'],fontSize=9,leading=11,spaceAfter=8)
    centered=ParagraphStyle('Centered',parent=styles['BodyText'],alignment=TA_CENTER,spaceAfter=8)
    report=solution.get('document_type')=='technical_report'; metadata=deliverable_identity(identity)
    memo=solution.get('document_type')=='memo'
    _check_required_figures(solution,rendering); page_budget=_body_page_budget(rendering); frame=_figure_frame_points(rendering)
    appendix_start:list[int]=[]

    class _AppendixMark(Flowable):
        """Zero-size marker that records the page the appendices begin on."""
        width=height=0
        def draw(self)->None:
            appendix_start.append(self.canv.getPageNumber())

    title=str(solution.get('title','Engineering Assignment'))
    title_page=bool(rendering.get('title_page',True))
    if memo:
        from reportlab.platypus.flowables import HRFlowable
        # Values sit in their own column, as a memo's do, rather than starting
        # wherever each label happens to end.
        rows=[[Paragraph(f'<b>{escape(label)}:</b>',styles['BodyText']),Paragraph(escape(value),styles['BodyText'])]
              for label,value in memo_header_rows(solution,metadata['display_name'])]
        header=Table(rows,colWidths=[0.75*inch,None],hAlign='LEFT')
        header.setStyle(TableStyle([('LEFTPADDING',(0,0),(-1,-1),0),('VALIGN',(0,0),(-1,-1),'TOP'),
                                    ('TOPPADDING',(0,0),(-1,-1),1),('BOTTOMPADDING',(0,0),(-1,-1),1)]))
        story.extend([header,Spacer(1,0.08*inch),HRFlowable(width='100%',thickness=0.75,color=colors.black),Spacer(1,0.14*inch)])
    elif report and title_page:
        story.extend([Spacer(1,1.1*inch),Paragraph(escape(title),styles['Title']),Spacer(1,0.35*inch)])
        details=solution.get('metadata',{}) if isinstance(solution.get('metadata',{}),dict) else {}
        for value in (details.get('course'),details.get('section'),metadata['display_name'],details.get('date')):
            if value: story.append(Paragraph(escape(str(value)),centered))
        if rendering.get('abstract',False) and not solution.get('abstract'): raise ValueError('course profile requires an abstract')
        if solution.get('abstract'):
            story.extend([Spacer(1,0.35*inch),Paragraph('Abstract',styles['Heading2'])])
            _paragraph(story,solution['abstract'],styles['BodyText'],Paragraph)
        story.append(PageBreak())
    else: story.append(Paragraph(escape(title),styles['Title']))

    def add_section(section,appendix=False):
        heading=str(section.get('heading','Appendix' if appendix else ''))
        if heading: story.extend([Paragraph(escape(heading),styles['Heading2']),Spacer(1,0.06*inch)])
        _paragraph(story,section.get('body',''),styles['BodyText'],Paragraph)
        equations=section.get('equations',[])
        if isinstance(equations,list):
            for equation in equations: story.append(Paragraph(escape(str(equation)),centered))
        tables=section.get('tables',[])
        if isinstance(tables,list):
            for item in tables:
                if not isinstance(item,dict): continue
                caption_value=Paragraph(escape(str(item['caption'])),caption) if item.get('caption') else None
                if caption_value is not None and rendering.get('table_captions_above',True): story.append(caption_value)
                headers,rows=item.get('headers',[]),item.get('rows',[])
                if not isinstance(headers,list) or not isinstance(rows,list) or not all(isinstance(row,list) for row in rows): raise ValueError('table headers and rows must be lists')
                data=([headers] if headers else [])+rows
                if data:
                    table=Table([[Paragraph(escape(str(cell)),styles['BodyText']) for cell in row] for row in data],repeatRows=1 if headers else 0)
                    commands=[('GRID',(0,0),(-1,-1),0.5,colors.black),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5)]
                    if headers: commands.append(('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E8E8E8')))
                    table.setStyle(TableStyle(commands)); story.append(table)
                    if caption_value is not None and not rendering.get('table_captions_above',True): story.append(caption_value)
                    story.append(Spacer(1,0.12*inch))
        figures=section.get('figures',[])
        if isinstance(figures,list):
            for item in figures:
                if not isinstance(item,dict): continue
                path=_safe_figure(run_root,item.get('path')); image=Image(str(path)); draw_width,draw_height=_figure_points(path,item,frame)
                figure_caption=Paragraph(escape(str(item['caption'])),caption) if item.get('caption') else None
                if figure_caption is not None and not rendering.get('figure_captions_below',True): story.append(figure_caption)
                image.drawWidth=draw_width; image.drawHeight=draw_height; image.hAlign='CENTER'; story.append(image)
                if figure_caption is not None and rendering.get('figure_captions_below',True): story.append(figure_caption)
        story.append(Spacer(1,0.12*inch))

    sections=solution.get('sections',[])
    if isinstance(sections,list):
        for section in sections:
            if isinstance(section,dict): add_section(section)
    appendices=solution.get('appendices',[])
    if isinstance(appendices,list) and appendices:
        story.append(PageBreak()); story.append(_AppendixMark())
        for appendix in appendices:
            if isinstance(appendix,dict): add_section(appendix,True)

    def page_number(canvas,doc):
        if rendering.get('number_body_pages',True) and (not (report and title_page) or doc.page>1):
            number=doc.page-1 if report and title_page else doc.page; canvas.saveState(); canvas.setFont('Helvetica',9); canvas.drawCentredString(letter[0]/2,0.55*inch,str(number)); canvas.restoreState()
    document=SimpleDocTemplate(str(output),pagesize=letter,rightMargin=margin,leftMargin=margin,topMargin=margin,bottomMargin=margin,author=metadata['display_name'],title=title)
    document.build(story,onFirstPage=page_number,onLaterPages=page_number)
    if page_budget is not None:
        cover=1 if (report and title_page) else 0
        last_body=(appendix_start[0]-1) if appendix_start else document.page
        body_pages=max(last_body-cover,0)
        if body_pages > page_budget:
            # The artifact exists but does not meet the course's stated page
            # limit.  Remove it rather than leave a non-compliant deliverable
            # on disk for a later stage to register as if it were acceptable.
            output.unlink(missing_ok=True)
            raise ValueError(f'rendered body is {body_pages} page(s) but the course profile allows at most {page_budget}')
    return output
