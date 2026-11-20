"""Write an editable Word summary of the current Rustmatics composition."""
from collections import Counter
from io import BytesIO
import re

import bpy

from . import map_prefabs, scene
from .core.project import atomic_write


INVENTORY_LIMIT = 50
DIAGNOSTIC_LIMIT = 20


def xml_text(value):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', '\ufffd', str(value))


def export(path, *, overwrite):
    try:
        from docx import Document
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt, RGBColor
    except ImportError as error:
        raise ValueError('Word export requires python-docx. Use a packaged build or run tools/setup_assets.py.') from error

    state = bpy.context.scene.ruster
    roots = scene.prefab_roots()
    validation = map_prefabs.validation_status()
    counts = Counter()
    labels = {}
    for root in roots:
        uid = str(root.get('ruster_uid', 'Unknown'))
        counts[uid] += 1
        collection = root.instance_collection
        if collection and collection.get('ruster_asset_name'):
            labels[uid] = collection['ruster_asset_name']

    document = Document()
    document.core_properties.title = 'Rustmatics Project Report'
    document.core_properties.author = 'Rustmatics'
    section = document.sections[0]
    section.left_margin = section.right_margin = Inches(.85)
    section.top_margin = section.bottom_margin = Inches(.75)
    document.styles['Normal'].font.size = Pt(11)
    title_style = document.styles['Title']
    title_style.font.color.rgb = RGBColor(0, 0, 0)
    title_properties = title_style.element.get_or_add_pPr()
    border = title_properties.find(qn('w:pBdr'))
    if border is not None:
        title_properties.remove(border)

    document.add_heading('Rustmatics Project Report', 0)
    document.add_paragraph(xml_text(state.title or 'Untitled'), style='Subtitle')
    document.add_paragraph(
        f'This composition contains {len(roots):,} prefab placements across {len(counts):,} prefab IDs. '
        f'The map world size is {state.map_size:,} m. '
        + ('Native Rust ground is present.' if state.native_ground else 'A map export will contain prefab placements only.')
    )

    document.add_heading('Map Export Validation', level=1)
    document.add_paragraph('Export checks passed.' if validation['valid'] else 'Export checks found errors.')
    for label, messages in (('Error', validation['errors']), ('Note', validation['notes'])):
        for message in messages[:DIAGNOSTIC_LIMIT]:
            document.add_paragraph(f'{label} · {xml_text(message)}', style='List Bullet')
        if len(messages) > DIAGNOSTIC_LIMIT:
            document.add_paragraph(f'{len(messages) - DIAGNOSTIC_LIMIT:,} additional {label.lower()}s.')
    document.add_paragraph('Rust server startup and gameplay require separate checks.')

    if counts:
        document.add_heading('Prefab Inventory', level=1)
        if len(counts) > INVENTORY_LIMIT:
            document.add_paragraph(f'Showing the {INVENTORY_LIMIT} most placed prefab IDs.')
        table = document.add_table(rows=1, cols=3)
        table.style = 'Light Shading Accent 1'
        table.autofit = False
        widths = (Inches(1.35), Inches(4.3), Inches(1.15))
        for column, width in zip(table.columns, widths):
            column.width = width
        header = table.rows[0]
        header._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
        rows = [(header, ('Prefab ID', 'Asset name', 'Placements'))]
        for uid, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:INVENTORY_LIMIT]:
            rows.append((table.add_row(), (uid, labels.get(uid, 'Name unavailable'), f'{count:,}')))
        for row, values in rows:
            row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
            for cell, width, value in zip(row.cells, widths, values):
                cell.width = width
                cell.text = xml_text(value)

    output = BytesIO()
    document.save(output)
    atomic_write(path, output.getvalue(), overwrite=overwrite)
    return {'path': str(path), 'valid': validation['valid'], 'prefab_count': len(roots),
            'native_ground': state.native_ground}
