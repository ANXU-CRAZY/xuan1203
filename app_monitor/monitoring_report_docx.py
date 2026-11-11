"""Editable Word report with locally rendered statistical figures."""
from functools import partial
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .monitoring_report_figures import figure

ASSETS = Path(__file__).with_name('report_assets')
BODY_FONT = '仿宋_GB2312'
HEADER_TEXT = '郑州大学地球科学与技术学院·郑州市自然事物地保护中心·方舟实验室'
COVER_NOTE = '本期数据概况见表1。本报告由黄河生态方舟平台小舟智能体生成，供监测工作参考和人工复核。'
TITLE_STYLES = ('Title', 'Heading 1', 'Heading 2', 'Caption')


def set_font(style, size, bold=False, family=BODY_FONT):
    style.font.name = family
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.italic = False
    style.font.color.rgb = RGBColor(0, 0, 0)
    fonts = style.element.get_or_add_rPr().rFonts
    for attribute in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme'):
        fonts.attrib.pop(qn('w:' + attribute), None)
    fonts.set(qn('w:eastAsia'), family)
    for border in style.element.findall('.//' + qn('w:pBdr')):
        border.getparent().remove(border)


def table(document, headers, rows, widths, *, row_spacing=3):
    result = document.add_table(rows=0, cols=len(headers))
    result.autofit = False
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'bottom', 'left', 'right', 'insideH', 'insideV'):
        item = OxmlElement('w:' + edge)
        item.set(qn('w:val'), 'single' if edge in ('top', 'bottom') else 'nil')
        item.set(qn('w:sz'), '12')
        item.set(qn('w:color'), '000000')
        borders.append(item)
    result._tbl.tblPr.append(borders)
    for column, width in zip(result.columns, widths):
        column.width = Cm(width)
    for index, values in enumerate([headers, *rows]):
        cells = result.add_row().cells
        for cell, value, width in zip(cells, values, widths):
            cell.width = Cm(width)
            cell.vertical_alignment = 1
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(row_spacing)
            p.paragraph_format.space_before = Pt(row_spacing)
            run = p.add_run(str(value))
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0, 0, 0)
            properties = cell._tc.get_or_add_tcPr()
            if index == 0:
                cell_borders = OxmlElement('w:tcBorders')
                bottom = OxmlElement('w:bottom')
                for key, val in [('val', 'single'), ('sz', '6'), ('color', '000000')]:
                    bottom.set(qn('w:' + key), val)
                cell_borders.append(bottom)
                properties.append(cell_borders)
        row_properties = cells[0]._tc.getparent().get_or_add_trPr()
        row_properties.append(OxmlElement('w:cantSplit'))
        if index == 0:
            row_properties.append(OxmlElement('w:tblHeader'))
    return result


def add_figure(doc, data, kind, caption, unit):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.keep_with_next = True
    shape = paragraph.add_run().add_picture(figure(data, kind, unit), width=Cm(16.4))
    shape._inline.docPr.set('descr', caption)
    doc.add_paragraph(caption, 'Caption').paragraph_format.keep_with_next = False


def set_title_color(doc):
    # Apply explicit black so Word themes cannot recolor titles and captions.
    for paragraph in doc.paragraphs:
        if paragraph.style.name in TITLE_STYLES:
            for run in paragraph.runs:
                run.font.color.rgb = RGBColor(0, 0, 0)


def add_synthesis(body, data, unit):
    current, previous = data['current'], data['previous']
    if not current['birds']:
        body('本期缺少可用于数量结构分析的已审核观测只次。应先核对日期范围、记录入库和审核进度，'
             '再根据调查日志判断哪些时段需要补充资料。现有数据无法支持对种群或生境变化的判断。')
        return

    peak = max(range(len(data['series'])), key=data['series'].__getitem__)
    peak_sites = data['site_series'][peak]
    most_sites = max(data['site_series'])
    site_review = (
        '只次峰值同时达到最大点位覆盖，应分点位回查高值是否由少数大群体记录贡献。'
        if peak_sites == most_sites
        else '只次峰值所在时段未达到最大点位覆盖，应优先核对高值是否集中于少数点位的大群体记录。'
    )
    body(
        f"第{peak + 1}{unit}的观测只次达到本期峰值，为 {data['series'][peak]:,} 只次，"
        f'这一时段有 {peak_sites:,} 个点位留有已审核记录，本期单{unit}最多为 {most_sites:,} 个点位（图1、图2）。'
        f'{site_review}点位数没有计入每个点位的访问频次和观察时长。'
    )

    top_species = data['top_species']
    bird_share = sum(row['birds'] for row in top_species) / current['birds']
    record_share = sum(row['records'] for row in top_species) / current['records']
    leader = top_species[0]
    species_review = (
        '这些物种的只次占比高于记录条数占比，应先复核高只次记录的群体计数和重复上报情况。'
        if round(bird_share, 3) > round(record_share, 3)
        else '应结合表3逐个核对主要物种的记录条数和单条记录数量，以识别高排序物种的主要数量来源。'
    )
    body(
        f'图3所列 {len(top_species)} 个物种贡献了 {bird_share:.1%} 的观测只次和 {record_share:.1%} 的记录条数。'
        f"其中{leader['name']}的只次最高，{leader['records']:,} 条记录共计 {leader['birds']:,} 只次。"
        f'{species_review}'
    )

    priority = ('国家一级', '国家二级')
    protected_birds = sum(data['protection'][level] for level in priority)
    protected_species = sum(data['protection_species'][level] for level in priority)
    protection_review = (
        '后续可按物种名录逐项复核鉴定资料，并优先补齐只出现于个别记录的物种证据。'
        if protected_species else '应结合重点物种的历史记录与本期覆盖范围，确定下一期的复查对象。'
    )
    body(
        f'国家一级和二级合计记录 {protected_species:,} 种、{protected_birds:,} 只次，'
        f"分别占本期记录物种数的 {protected_species / current['species']:.1%} "
        f"和累计观测只次的 {protected_birds / current['birds']:.1%}（图4、图5）。"
        f'{protection_review}'
    )

    if previous['records']:
        body(
            f"本期平均每条记录 {current['birds'] / current['records']:.1f} 只次，上年同期为 "
            f"{previous['birds'] / previous['records']:.1f} 只次，两期记录分别覆盖 "
            f"{current['sites']:,} 和 {previous['sites']:,} 个点位（表2）。"
            '结合两组指标可判断是否需要核对点位范围、记录频次或单条大群体记录。'
            '每条记录的只次是入库资料的描述性均值，解读时仍需查阅实际调查投入。'
        )


def build_docx(period, data, assessment, source, *, generated_on):
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(2.2), Cm(1.8)
    section.left_margin, section.right_margin = Cm(2.3), Cm(2.3)
    section.header_distance, section.footer_distance = Cm(.8), Cm(.8)
    for name, size, bold in [('Normal', 10.5, False), ('Title', 25, True),
                             ('Heading 1', 16, True), ('Heading 2', 12, True),
                             ('Caption', 9, False)]:
        set_font(doc.styles[name], size, bold, '黑体' if name != 'Normal' else BODY_FONT)
    note = doc.styles.add_style('Report Note', WD_STYLE_TYPE.PARAGRAPH)
    note.base_style = doc.styles['Normal']
    set_font(note, 9)
    # Declare an available alternate while retaining the requested GB font name.
    font_part = doc.part.rels.part_with_reltype('http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable')
    fonts = parse_xml(font_part.blob)
    if not any(font.get(qn('w:name')) == BODY_FONT for font in fonts):
        font = OxmlElement('w:font')
        font.set(qn('w:name'), BODY_FONT)
        alternative = OxmlElement('w:altName')
        alternative.set(qn('w:val'), '仿宋')
        font.append(alternative)
        fonts.append(font)
        from lxml import etree
        font_part._blob = etree.tostring(fonts, xml_declaration=True, encoding='UTF-8', standalone=True)
    body_style = doc.styles.add_style('Report Body', WD_STYLE_TYPE.PARAGRAPH)
    body_style.base_style = doc.styles['Normal']
    set_font(body_style, 12)
    body_style.paragraph_format.line_spacing = 1.25
    body_style.paragraph_format.space_after = Pt(6)
    body_style.element.get_or_add_pPr().get_or_add_ind().set(qn('w:firstLineChars'), '200')
    body = partial(doc.add_paragraph, style=body_style)
    doc.styles['Normal'].paragraph_format.space_after = Pt(6)
    doc.styles['Caption'].paragraph_format.keep_with_next = True
    for name in ('Heading 1', 'Heading 2'):
        doc.styles[name].paragraph_format.keep_with_next = True
    doc.core_properties.title = period['title']
    doc.core_properties.author = '黄河生态方舟'
    doc.styles['Header'].paragraph_format.tab_stops.clear_all()
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    header.paragraph_format.space_after = Pt(0)
    header.paragraph_format.tab_stops.add_tab_stop(Cm(16.4), WD_TAB_ALIGNMENT.RIGHT)
    header_text = header.add_run(HEADER_TEXT)
    header_text.font.size = Pt(8)
    lift = OxmlElement('w:position')
    lift.set(qn('w:val'), '8')
    header_text._element.get_or_add_rPr().append(lift)
    header.add_run('\t').add_picture(str(ASSETS.parent / 'static/app_monitor/img/logo.png'), height=Cm(.75))
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run('鸟类监测报告   ·   ')
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    footer._p.append(field)
    for run in footer.runs:
        run.font.size = Pt(8)

    doc.add_paragraph(period['title'], 'Title')
    doc.add_paragraph('平台已审核鸟类观测数据汇编与分析')
    doc.add_paragraph(f"统计时段  {period['start']:%Y年%m月%d日} — {period['end']:%Y年%m月%d日}")
    doc.add_paragraph('本期尚未结束，报告为截至统计日的阶段性结果。' if period['partial']
                      else '本报告采用所选完整日历时段。')
    paragraph = doc.add_paragraph()
    paragraph.add_run().add_picture(str(ASSETS / 'wetland-cover.png'), width=Cm(16.4))
    doc.add_paragraph('黄河湿地主题插画  AI 生成示意图', 'Caption')
    current, previous = data['current'], data['previous']
    doc.add_paragraph('表1  本期监测数据概况', 'Caption')
    table(doc, ['观测记录', '累计观测只次', '记录物种', '记录点位'], [[
        f"{current['records']:,}", f"{current['birds']:,}", str(current['species']), str(current['sites']),
    ]], [4.1]*4)
    doc.add_paragraph('数据来源  黄河生态方舟平台已审核观测记录')
    doc.add_paragraph(f'生成日期  {generated_on:%Y年%m月%d日}    文本方式  {source}')
    doc.add_paragraph(COVER_NOTE, 'Report Note')

    doc.add_heading('监测任务与资料来源', 1)
    body(
        '本报告围绕所选时段的鸟类观测记录开展资料汇编，回答本期记录覆盖如何、观测数量在何时集中、'
        '哪些物种及保护等级构成主要记录，以及与上年同期相比有哪些需要进一步核实的变化。'
        '报告以平台审核后的观测资料为依据，将统计结果、解释与后续监测任务衔接，供调查组织、记录复核和资料归档使用。'
    )
    doc.add_heading('统计范围与审核条件', 2)
    body(
        f"本期按观测日期纳入 {period['start']:%Y年%m月%d日} 至 {period['end']:%Y年%m月%d日} 的已审核记录。"
        '统计范围为平台全部符合条件的观测资料，不沿用页面临时设置的地图视域或保护等级筛选。'
        '待审核和已驳回记录不计入本报告。审核状态如在以后发生变化，重新生成的报告可能随之更新。'
    )
    body(
        '记录条数反映入库资料的规模，累计观测只次是各条记录数量的加总，物种数按物种编号去重，'
        '监测点位数按点位编号去重。相同物种或相同个体可能在不同日期被多次记录，因此观测只次不能替代独立个体数。'
        '阅读结果时，应把这几项指标分别用于判断资料量、物种覆盖与点位覆盖。'
    )
    doc.add_heading('汇总方法与比较口径', 2)
    body(
        '年度报告按月份汇总，月度报告按日序汇总。各时段均使用相同的审核条件，空白时段以零值表示。'
        '零值只说明当前入库记录中没有对应观测只次，尚不能区分未开展调查、没有发现鸟类、尚未上报或尚未审核等原因。'
        '后续解释应结合调查日志核实这些环节。'
    )
    body(
        '同期对照采用上年相应日历时段。对于尚未结束的年度或月份，比较范围同步截取到对应日期，'
        '闰日差异按上年该月最后一个有效日期处理。基期指标为零时不计算变化率。'
        '报告未开展显著性检验、检测概率估计或单位调查工作量校正，所有变化率均为描述性指标。'
    )
    doc.add_heading('现场方法信息的使用边界', 2)
    body(
        '现有记录字段可以支持物种、日期、数量及审核状态的汇总，但没有完整提供每次观察时长、样线长度、'
        '调查人员配置、天气和观察设备等工作量信息。因此，本报告不据此重建具体现场调查流程。'
        '这些信息应由调查组织单位在复核时补充，以判断不同点位和不同时段的记录是否具有可比性。'
    )

    doc.add_heading('监测总体结果与同期比较', 1)
    body(
        f"本期共汇集已审核记录 {current['records']:,} 条，累计观测 {current['birds']:,} 只次，"
        f"涉及 {current['species']} 个物种和 {current['sites']} 个监测点位。"
        '只次为各条记录数量的累加，可能包含同一个体的多次观测。同期对照见表2，时序变化见图1。'
    )
    doc.add_heading('同期对照', 2)
    body(f"对照时段为 {period['previous_start']:%Y-%m-%d} 至 {period['previous_end']:%Y-%m-%d}。")
    rows = []
    for label, field in [('观测记录', 'records'), ('累计观测只次', 'birds'), ('记录物种', 'species'), ('记录点位', 'sites')]:
        change = f"{(current[field] / previous[field] - 1):+.1%}" if previous[field] else '基期为零，未计算'
        rows.append([label, f"{previous[field]:,}", f"{current[field]:,}", change])
    doc.add_paragraph('表2  本期与上年同期监测指标对照', 'Caption')
    table(doc, ['指标', '上年同期', '本期', '记录变化率'], rows, [4, 3.2, 3.2, 6])
    for paragraph in assessment['comparison']:
        body(paragraph)
    body(
        '复核同比差异时，建议依次检查记录条数、点位数、物种数与累计观测只次是否同向变化。'
        '记录条数与观测只次共同变化时，应关注调查投入和大群体记录的影响；点位数变化时，应先核对覆盖范围；'
        '物种数变化时，应检查物种鉴定、名录维护和零星记录审核情况。'
        '这些核查用于明确差异来源，不预设已经发生生态系统变化。'
    )
    doc.add_heading('观测只次的时序分布', 1)
    active_buckets = sum(value > 0 for value in data['series'])
    unit = '月' if period['kind'] == 'annual' else '日'
    if current['birds']:
        peak = max(range(len(data['series'])), key=data['series'].__getitem__)
        body(
            f"本期纳入 {len(data['series'])} 个统计{unit}，其中 {active_buckets} 个{unit}有已审核观测只次。"
            f"最高值出现在第 {peak+1} {unit}，累计观测 {data['series'][peak]:,} 只次，"
            f"占本期累计观测只次的 {data['series'][peak]/current['birds']:.1%}。本期与上年同期的时序分布见图1。"
        )
    else:
        body('本期没有可用于绘制观测数量分布的已审核只次。图1保留统计时间轴，以便复核时识别资料空白。')
    add_figure(doc, data, 'timeline', '图1  本期与上年同期观测只次时序变化', unit)
    doc.add_paragraph('注：实线为本期，虚线为上年同期。零值表示该时段没有已审核观测只次。', 'Report Note')
    body(
        '时序图用于识别需要复核的高值、低值和资料空白区间。对单个高值时段，应回查是否由少数大群体记录主导，'
        '是否存在集中补录、重复记录或调查活动增多等情况。对连续空白时段，应先确认调查和审核覆盖是否持续，'
        '再决定是否需要安排补充调查。'
    )
    body(
        '即使图中出现相近的年度高值时段，也不能仅凭记录量判断迁徙开始、停歇持续时间或繁殖活动。'
        '要区分这些过程，需要更连续的调查、物种生活史信息以及可比较的观察工作量。'
        '本图的直接用途是明确资料中的时间分布，并为下一期调查安排提供可核查的问题清单。'
    )
    doc.add_heading('点位记录覆盖', 2)
    body(
        f'图2按{unit}统计至少有一条已审核观测记录的点位数，同一点位在同一时段只计一次。'
        '将图2与图1对照，可以检查观测只次高值是否伴随更广的点位覆盖。'
        '没有入库记录的调查无法体现在图中，点位数也不反映单个点位的调查频次或时长。'
    )
    add_figure(doc, data, 'sites', '图2  各时段有已审核记录的点位数', unit)

    doc.add_heading('物种组成与主要记录物种', 1)
    body('累计观测只次前八位物种见图3与表3，完整物种记录清单见附表1。排序采用累计观测只次，记录条数同时列出，以便区分多次记录与少数大群体观测的不同影响。')
    add_figure(doc, data, 'species', '图3  累计观测只次前八位物种排序', unit)
    doc.add_paragraph('表3  主要记录物种及其观测数量', 'Caption')
    rows = [[str(index), row['name'], row['level'], f"{row['birds']:,}", f"{row['records']:,}"]
            for index, row in enumerate(data['top_species'], 1)]
    table(doc, ['序号', '物种', '保护分类', '观测只次', '记录条数'], rows, [1.2, 5.1, 3.6, 3.2, 3.3])
    if current['birds']:
        share = sum(row['birds'] for row in data['top_species']) / current['birds']
        body(f"图3所列物种合计占本期累计观测只次的 {share:.1%}。该比例描述记录的数量集中程度，不能据此直接确定调查区域的群落优势度。")
    doc.add_heading('保护等级构成与记录复核', 1)
    body('保护等级按平台统一分类汇总。图4给出各类累计观测只次及其占比，图5给出各类有已审核记录的物种数。'
         '两个指标分别用于识别记录数量集中在哪些类别，以及各类记录覆盖了多少种鸟类。')
    add_figure(doc, data, 'protection', '图4  累计观测只次的保护等级构成', unit)
    add_figure(doc, data, 'protection_species', '图5  各保护等级的记录物种数', unit)
    first, second = data['protection']['国家一级'], data['protection']['国家二级']
    body(
        f"本期国家一级类累计观测 {first:,} 只次，国家二级类累计观测 {second:,} 只次。"
        '这两类记录可作为优先复核对象，复核内容应包括物种鉴定依据、观测日期、原始图像和群体计数说明。'
        '对于数量较少但保护等级较高的记录，资料完整性同样重要，不应因其对总量贡献较低而忽略。'
    )
    for paragraph in assessment['results']:
        body(paragraph)
    body(
        '分类中的“其他”用于容纳平台未归入前三类的记录，不作为物种濒危程度的正式评价。'
        '保护名录与受威胁等级属于不同体系，报告未引入独立的受威胁等级资料。'
        '正式使用时，应核对平台物种信息及适用名录版本，避免将分类标签解释为完整的保护状况判断。'
    )

    doc.add_heading('综合分析与后续监测建议', 1)
    add_synthesis(body, data, unit)
    doc.add_heading('后续监测安排', 2)
    for paragraph in assessment['recommendations']:
        body(paragraph)
    body(
        '建议在下一期汇总前，形成已完成复核、待补充资料和需现场确认三类工作记录，并注明责任环节与完成情况。'
        '对于需要持续关注的物种，应尽量使用固定的时间窗口和稳定的调查路线，记录实际观察投入。'
        '当人员、设备、路线或统计规则发生调整时，将变化与当期数据一并归档，便于今后解释跨期差异。'
    )
    doc.add_heading('复核与共享说明', 2)
    body(
        '对外使用前，请复核物种鉴定、重复记录、审核状态与时间覆盖。跨期比较时，应核对调查工作量是否一致。'
        '本报告不导出记录坐标、缓冲区中心坐标、点位名称或自由描述。'
    )
    body(
        f'正文研判采用{source}。所有统计值和图表由服务器计算，'
        '文本生成失败时使用平台数据摘要。图表图像可直接在 Word 中查看，正文及表格可编辑。'
    )
    inventory = data.get('species_inventory', data['top_species'])
    doc.add_heading('附录 物种记录清单', 1)
    body('附表1列出本期全部有已审核观测记录的物种汇总，按累计观测只次降序排列。中文名与保护分类采用平台当前物种资料，正式使用前请复核。')
    doc.add_paragraph('附表1  本期物种记录清单', 'Caption').paragraph_format.keep_with_next = True
    table(doc, ['序号', '物种', '保护分类', '观测只次', '记录条数'], [
        [str(index), row['name'], row['level'], f"{row['birds']:,}", f"{row['records']:,}"]
        for index, row in enumerate(inventory, 1)
    ], [1.2, 5.1, 3.6, 3.2, 3.3], row_spacing=2.5)
    set_title_color(doc)
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
