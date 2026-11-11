"""Statistical figures for Word monitoring reports."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.ft2font import FT2Font
from matplotlib.ticker import MaxNLocator, StrMethodFormatter


TEAL = '#007F79'
SLATE = '#647685'
PROTECTION_COLORS = ('#6B4D92', '#BC6C24', '#168B83', '#A9BEC8')


@lru_cache(maxsize=1)
def chinese_font():
    for path in (
        Path('C:/Windows/Fonts/msyh.ttc'),
        Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
        Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'),
    ):
        if path.is_file():
            return str(path), frozenset(FT2Font(str(path)).get_charmap())
    return None, frozenset()


def localized(labels, fallback):
    path, glyphs = chinese_font()
    if path and all(ord(char) in glyphs for text in labels for char in text):
        return labels, FontProperties(fname=path, size=8)
    return fallback, FontProperties(size=8)


def count_axis(ax, axis):
    axis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    axis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
    ax.set_axisbelow(True)


def time_chart(fig, ax, data, unit, kind):
    labels, font = localized([f'序{unit}', '观测只次', '记录点位数', '本期', '上年同期'],
                             ['Month' if unit == '月' else 'Day', 'Bird observations', 'Sites with records',
                              'Current period', 'Previous year'])
    current = data['series'] if kind == 'timeline' else data['site_series']
    positions = range(1, len(current) + 1)
    if kind == 'timeline':
        previous = data['previous_series']
        ax.plot(positions, current, color=TEAL, linewidth=1.65, marker='o', markersize=3, label=labels[3])
        ax.plot(range(1, len(previous) + 1), previous, color=SLATE, linewidth=1.35, linestyle='--', label=labels[4])
        ax.legend(loc='lower left', bbox_to_anchor=(0, 1.02), ncols=2, frameon=False, borderaxespad=0, prop=font)
        last = max(len(current), len(previous))
        ax.set_ylabel(labels[1], fontproperties=font)
        fig.subplots_adjust(top=.82)
    else:
        ax.bar(positions, current, color=TEAL, width=.68)
        last = len(current)
        ax.set_ylabel(labels[2], fontproperties=font)
    ticks = list(range(1, last + 1, 3 if last > 15 else 1))
    if ticks[-1] != last:
        ticks.append(last)
    ax.set(xticks=ticks, xlim=(.5, last + .5), ylim=(0, max(ax.get_ylim()[1], 1)))
    ax.set_xlabel(labels[0], fontproperties=font)
    count_axis(ax, ax.yaxis)
    ax.grid(axis='y', color='#E0E5E7', linewidth=.65)


def horizontal_counts(fig, ax, labels, font, values, colors, unit):
    positions = range(len(values))
    ax.barh(positions, values, height=.57, color=colors)
    ax.set_yticks(list(positions), labels, fontproperties=font)
    ax.invert_yaxis()
    ax.spines['left'].set_visible(False)
    ax.tick_params(axis='y', length=0)
    ax.set_xlim(0, max(*values, 1) * 1.24)
    for position, value in zip(positions, values):
        ax.annotate(f'{value:,}', (value, position), xytext=(4, 0), textcoords='offset points',
                    va='center', fontsize=8, color='#222222')
    axis_label, axis_font = localized([unit], ['Bird observations' if unit == '观测只次' else 'Species'])
    ax.set_xlabel(axis_label[0], fontproperties=axis_font)
    fig.subplots_adjust(left=.20, right=.96)
    count_axis(ax, ax.xaxis)


def protection_donut(fig, ax, data):
    values = list(data['protection'].values())
    labels, font = localized(list(data['protection']), ['Class I', 'Class II', 'Three-value', 'Other'])
    total = sum(values)
    ax.set_axis_off()
    fig.subplots_adjust(left=.04, right=.57, bottom=.04, top=.96)
    if total:
        ax.pie(values, colors=PROTECTION_COLORS, startangle=90, counterclock=False,
               wedgeprops={'width': .36, 'edgecolor': 'white', 'linewidth': .45})
    else:
        ax.pie([1], colors=['#E6EBED'], wedgeprops={'width': .36})
    ax.text(0, .075, f'{total:,}', ha='center', va='center', fontsize=14, weight='bold')
    unit, unit_font = localized(['观测只次'], ['observations'])
    ax.text(0, -.17, unit[0], ha='center', va='center', fontproperties=unit_font)
    for index, (label, value, color) in enumerate(zip(labels, values, PROTECTION_COLORS)):
        y = .77 - index * .18
        ax.plot(1.13, y, marker='s', markersize=6, color=color, transform=ax.transAxes, clip_on=False)
        ax.text(1.23, y, label, va='center', transform=ax.transAxes, fontproperties=font)
        detail = f'{value:,}  ({value / total:.1%})' if total else '0'
        ax.text(2.41, y, detail, ha='right', va='center', transform=ax.transAxes, fontsize=8)


def figure(data, kind, unit, *, format='png'):
    fig = Figure(figsize=(6.45, 2.10 if kind in ('species', 'protection') else 1.85))
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    fig.subplots_adjust(left=.14, right=.96, bottom=.24, top=.94)
    ax.spines[['right', 'top']].set_visible(False)
    ax.spines[['left', 'bottom']].set_linewidth(.65)
    ax.tick_params(labelsize=8, length=3, width=.65)
    if kind in ('timeline', 'sites'):
        time_chart(fig, ax, data, unit, kind)
    elif kind == 'species':
        rows = data['top_species']
        if rows:
            labels, font = localized([row['name'] for row in rows], [f'{i+1:02}' for i in range(len(rows))])
            horizontal_counts(fig, ax, labels, font, [row['birds'] for row in rows], TEAL, '观测只次')
        else:
            labels, font = localized(['本期无已审核记录'], ['No approved records in this period'])
            ax.set_axis_off()
            ax.text(.5, .5, labels[0], ha='center', va='center', transform=ax.transAxes, fontproperties=font)
    elif kind == 'protection':
        protection_donut(fig, ax, data)
    elif kind == 'protection_species':
        richness = data['protection_species']
        labels, font = localized(list(richness), ['Class I', 'Class II', 'Three-value', 'Other'])
        horizontal_counts(fig, ax, labels, font, list(richness.values()), PROTECTION_COLORS, '物种数')

    buffer = BytesIO()
    fig.savefig(buffer, format=format, dpi=300)
    buffer.seek(0)
    return buffer
