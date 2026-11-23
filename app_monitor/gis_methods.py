"""GIS method selection for GeoStudio. Native IDs refer to GeoLibre's processing registry.

Method distinctions follow the local gis.skill vector, raster, interpolation and spatial
statistics references. Whitebox search phrases are discovery queries, never execution IDs.
"""
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Method:
    name: str
    terms: str
    native: str
    compatible: str
    guidance: str
    raster: bool = False


METHODS = (
    Method('凸包', '凸包|最小凸多边形|convex hull|包住所有点', 'convex-hull', 'convex_hull',
           '用输入要素的最外围顶点构建凸多边形；至少需要三个不共线位置。凸包不代表实际栖息地边界。'),
    Method('质心', '质心|几何中心|centroid', 'centroids', 'centroids',
           '每个要素生成几何中心。凹形要素的质心可能落在外部，若要求面内标注点应另查面内点方法。'),
    Method('缓冲区', '缓冲|沿线两侧|周边范围|周围.*公里|buffer', 'buffer', 'buffer',
           '输入点、线或面和距离。把公里换算为米；多个对象是否融合取决于用户要逐对象还是整体范围。'),
    Method('按位置筛选', '面内点|范围内的.*点|筛.*区内|落在.*内|按位置选择|空间选择', 'select-by-location', 'points_within',
           '保留满足空间关系的原要素。兼容模式支持点落面内；不产生裁切碎片。'),
    Method('按属性筛选', '按属性|按字段筛|筛选.*大于|筛选.*小于|select by value', 'select-by-value', '',
           '核对字段、类型和条件。大于与大于等于有别，空值需单独判断。筛选成果用作后续分析的输入。'),
    Method('裁剪', '裁剪|裁切|剪裁|沿.*边界切|clip', 'clip', 'clip',
           '按掩膜切开输入几何，保留输入属性。当前矢量 clip 接受面和面。若目标是选点用位置筛选。'),
    Method('相交', '相交|交集|重叠部分|公共部分|intersect', 'intersection', 'intersection',
           '两个面图层，输出重叠面积及双方属性。只要求裁边时用裁剪。'),
    Method('擦除', '擦除|差集|挖掉|扣除|erase|difference', 'difference', 'difference',
           '输入面减去扣除面。A 减 B 有方向，输入与掩膜无法区分时询问。'),
    Method('联合叠加', '并集|联合叠加|union', 'union', 'union', '按两层覆盖关系求并集；与追加要素或按字段融合区分。'),
    Method('融合', '融合|消除内部边界|dissolve', 'dissolve', 'dissolve',
           '明确全部融合还是按字段分组。兼容模式仅支持全部面融合；几何融合不能代替数量求和。'),
    Method('合并图层', '合并图层|追加要素|merge layers', 'merge-layers', '',
           '将同类图层的要素追加到一个图层，检查属性字段和几何类型。保留重叠或边界的现状。'),
    Method('空间连接', '空间连接|空间关联|挂接.*属性|归属.*行政区|spatial join', 'spatial-join', '',
           '确认目标和连接图层、空间谓词、一对多关系及未匹配记录。普通属性连接不能代替空间关系。'),
    Method('分组汇总', '分组|分类汇总|汇总统计|每.*合计|summary statistics', 'aggregate', '',
           '确定分组键和统计字段。计行、求和、物种去重意义不同。按真实参数定义选择，核对各组总量。'),
    Method('反距离权重插值', '反距离|反距权|\\bidw\\b|插值|估算.*未测', 'idw interpolation', 'idw',
           '输入测量点与连续数值字段。排除编号和经纬度，多个候选先问字段；核对距离单位、网格大小和输出范围。精度评价需独立验证点。', True),
    Method('核密度', '核密度|点密度|热力图|密集程度|哪里最密|哪些地方最密|扎堆的地方|kernel density', 'kernel-density', '',
           '点位分布密度，明确带宽和可选权重；密度高值不能解释为显著热点。'),
    Method('显著热点', '显著热点|冷热.?点|getis|gi\\*', 'getis-ord-gi', '',
           '要求数值指标、空间权重或邻域及显著性判断。使用返回的统计量与显著性字段；不能拿核密度替代。'),
    Method('全局空间自相关', '全局.*莫兰|全局.*自相关|global moran', 'global-morans-i', '',
           '检验整体属性空间自相关。指定数值字段和权重。全局指标不能定位局部异常。'),
    Method('局部空间自相关', '局部.*莫兰|局部.*自相关|lisa|local moran|高高集聚', 'local-morans-i', '',
           '输出局部聚类与离群分类及显著性，需数值字段和邻域定义。'),
    Method('平均最近邻', '平均最近邻|平均最邻近|扎堆还是|聚集还是分散|average nearest neighbor', 'average-nearest-neighbor', '',
           '检验点分布，核对研究区面积和距离单位；解释观测/期望距离、比率及实际返回的显著性。'),
    Method('坡度', '坡度|哪里陡|陡峭|slope', 'slope from elevation DEM', '',
           '输入高程栅格，检查水平与垂直单位。确认坡度角或百分比，坡向和山体阴影不能替代坡度。', True),
    Method('水文汇流', '流向|水流往哪|汇流|河网提取|汇水|集水区|流量累积', 'fill depressions / D8 pointer / flow accumulation', '',
           '根据目标选择填洼、流向、汇流累积。提河网需阈值及单位；划汇水区还需出水口。用上一阶段实际产物。', True),
    Method('分区统计', '分区统计|zonal|每.*平均高程', 'zonal statistics', '',
           '明确分区 ID、值栅格、统计量及 NoData。栅格像元大小、原点、覆盖范围应一致。', True),
    Method('重采样', '重采样|改变分辨率|resampl', 'resample raster', '',
           '分类数据保留类别，连续面按目的选择插值。像元总量粗化需要聚合求和，不能只改变分辨率。', True),
)


def matching_methods(message):
    return [method for method in METHODS if re.search(method.terms, message, re.I)
            and not (method.compatible == 'idw' and re.search(r'克里金|kriging|样条', message, re.I))]


def guidance(message, *, native, tools=()):
    methods = matching_methods(message)
    if native:
        general = ('用中文回答。先读当前图层、字段、单位。地图算法的图层参数只用真实 id，SQL 表名只用于 SQL。'
                   '方法咨询只解释；用户需要执行时，用当前声明的工具实际操作地图。'
                   '先发现算法，再按返回的 id、参数签名和图层 id 执行。复合任务按依赖引用实际产物。'
                   '按要求的统计口径与交付范围执行；只问记录数时只统计记录数。'
                   '方法不同或关键输入缺失时只问影响结论的问题。根据工具真实结果报告，保留当前底图。')
    else:
        general = '只用本模式列出的可执行步骤。某个必需方法不可用时返回空计划；禁止用相近工具冒充。'
    lines = [general]
    if '热点' in message and not any(t in message.lower() for t in ('显著', 'gi*', '密度', 'getis')):
        lines.append('单说热点时先辨明要显示记录密集处，还是检验带数值属性的显著冷热区；询问用户目的。')
    if re.search(r'克里金|kriging|样条', message, re.I):
        lines.append('严格按所要求的插值方法查询当前工具目录；兼容模式只有 IDW，不能用 IDW 替代克里金或样条。')
    for m in methods:
        if native:
            discover = 'list_whitebox_tools' if m.raster else 'list_algorithms'
            execute = 'run_whitebox_tool' if m.raster else 'run_algorithm'
            route = (f'{discover} 检索 {m.native}，确认可用后 {execute}'
                     if discover in tools and execute in tools else '当前调用未声明相应发现及执行工具')
        else:
            route = m.compatible or '仅原生工作台可查询此方法'
        lines.append(f'{m.name}：{route}。{m.guidance}')
    return '\n'.join(lines)


def direct_plan(message, layers):
    """Resolve unambiguous, whole commands; leave qualifiers and compound tasks to the planner."""
    command = re.sub(r'[\s“”「」《》]', '', unicodedata.normalize('NFKC', message)).strip('。!?')
    command = re.sub(r'^(?:请帮我|帮我|请)', '', command)
    aliases = {}
    for layer in layers:
        if layer.get('type') not in ('', 'geojson', None):
            continue
        name = re.sub(r'\s', '', unicodedata.normalize('NFKC', layer['name']))
        for alias in {name, re.sub(r'[（(][^（）()]*[）)]$', '', name)} - {''}:
            aliases.setdefault(alias, set()).add(layer['ref'])
    if not aliases:
        return None
    # Bind actual layer names before parsing the operation: names may contain GIS terms.
    names = '|'.join(map(re.escape, sorted(aliases, key=len, reverse=True)))
    ref = '(?:' + names + ')'
    # A point-in-buffer chain consumes R1 and counts only the filtered rows (R2).
    distance_pattern = r'(?P<distance>\d+(?:\.\d+)?)(?P<unit>千米|公里|米)'
    chain = re.fullmatch(rf'(?:给|为|对)?(?P<line>{ref})(?:做|创建|建立|生成){distance_pattern}(?:的)?缓冲区'
                         rf'[，,、。]?(?:再)?(?:筛出|筛选|提取)(?:其中|里面|缓冲区内|区内)(?:的)?(?P<points>{ref})'
                         r'(?P<count>[，,。]?(?:并|再|然后)统计(?:记录数|条数|点数))?', command)
    if chain:
        if any(len(aliases[chain[k]]) != 1 for k in ('line', 'points')):
            return {'steps': [], 'message': '同名图层无法区分，请使用完整图层名。'}
        meters = float(chain['distance']) * (1 if chain['unit'] == '米' else 1000)
        if not 1 <= meters <= 100000:
            return {'steps': [], 'message': '缓冲距离须在 1 米至 100 公里之间。'}
        steps = [{'tool': 'buffer', 'layer': next(iter(aliases[chain['line']])), 'meters': meters},
                 {'tool': 'points_within', 'layer': next(iter(aliases[chain['points']])), 'area': 'R1'}]
        if chain['count']:
            steps.append({'tool': 'count', 'layer': 'R2'})
        return {'steps': steps, 'message': ''}
    commands = [
        (rf'从(?P<layer>{ref})(?:中)?(?:扣除|擦除|挖掉)(?P<area>{ref})', 'difference'),
        (rf'(?:求|提取|计算)?(?P<layer>{ref})(?:与|和|跟)(?P<area>{ref})(?:的)?(?:交集|公共部分|重叠部分)', 'intersection'),
        (rf'用(?P<area>{ref})(?:裁剪|裁切)(?P<layer>{ref})', 'clip'),
        (rf'(?:筛出|筛选|提取)(?P<area>{ref})(?:范围)?内的(?P<layer>{ref})', 'points_within'),
        (rf'(?:只保留|保留)(?:落在)?(?P<area>{ref})(?:范围)?(?:内|里面)的(?P<layer>{ref})', 'points_within'),
        (rf'(?:给|为|对)?(?P<layer>{ref})(?:做|建|创建|建立|生成|画)?(?:一个)?'
         r'(?P<distance>\d+(?:\.\d+)?)(?P<unit>千米|公里|米)(?:的)?缓冲区', 'buffer'),
        (rf'(?:沿着?|围绕)(?P<layer>{ref})(?:两侧|周围)?(?:划出|画出|画)?{distance_pattern}(?:的)?范围', 'buffer'),
        (rf'(?:求|提取|计算)(?P<layer>{ref})(?:的)?(?:质心|几何中心)', 'centroids'),
        (rf'(?:求|提取|计算)(?P<layer>{ref})(?:的)?凸包', 'convex_hull'),
    ]
    for pattern, tool in commands:
        match = re.fullmatch(pattern, command)
        if not match:
            continue
        step = {'tool': tool}
        for key in ('layer', 'area'):
            if key not in match.groupdict():
                continue
            refs = aliases[match[key]]
            if len(refs) != 1:
                return {'steps': [], 'message': f'有多个图层匹配“{match[key]}”，请给出完整图层名。'}
            step[key] = next(iter(refs))
        if tool == 'buffer':
            step['meters'] = float(match['distance']) * (1 if match['unit'] == '米' else 1000)
            if not 1 <= step['meters'] <= 100000:
                return {'steps': [], 'message': '缓冲距离须在 1 米至 100 公里之间。'}
        return {'steps': [step], 'message': ''}
    return None


def unsupported_request(message, layers):
    # Layer names may themselves be method names (e.g. "坡度"). Strip them first.
    for layer in sorted(layers, key=lambda l: len(l['name']), reverse=True):
        if layer['name']:
            message = message.replace(layer['name'], '')
    # Keep qualified/negated instructions with the planner instead of reporting a false conflict.
    if re.search('不要|无需|不用|排除|不做|不进行|不需要', message):
        return ''
    explicit = re.search(r'(克里金|kriging|样条插值|核密度|kernel density|Getis[- ]Ord|Gi\*|'
                         r'全局莫兰|局部莫兰|Moran.?s I|分区统计|空间连接|D8流向|按属性筛选|合并图层|'
                         r'(?:计算|求|生成|提取)坡度)', message, re.I)
    return (f'当前兼容地图没有“{explicit[0]}”的执行工具。请在原生地图模式查询相应算法。'
            if explicit else '')


def check_geometry(steps, layers):
    shapes = {l['ref']: set(l.get('geometry', [])) for l in layers}
    polygons = {'Polygon', 'MultiPolygon'}
    lines = {'LineString', 'MultiLineString'}
    for index, step in enumerate(steps, 1):
        tool = step['tool']
        left = shapes.get(step.get('layer'), set())
        area = shapes.get(step.get('area'), set())
        if area and not area <= polygons:
            return '范围图层需要面几何，请选择保护区或其他边界面。'
        if tool in ('clip', 'intersection', 'difference', 'union', 'dissolve') and left and not left <= polygons:
            return '此面叠加工具需要面图层；筛选边界内的点可以用按位置筛选。'
        if tool in ('idw', 'points_within') and left and left != {'Point'}:
            return '这项操作需要点图层，请指定采样点或观测点。'
        if tool == 'smooth' and left and not left <= (lines | polygons):
            return '平滑处理需要线或面图层。'
        output = {'buffer': polygons, 'centroids': {'Point'}, 'idw': polygons, 'points_within': {'Point'},
                  'convex_hull': polygons, 'bounding_box': polygons, 'extract_vertices': {'Point'}}
        shapes[f'R{index}'] = output.get(tool, left)
    return ''
