"""Convert supplied OviO v105 point/folder files without dropping records.

Private/versioned format: unknown objects, ambiguous point tails, truncation and
folder-count mismatches fail closed. Source coordinates are preserved verbatim.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct


def u32(data, pos):
    if pos+4 > len(data):
        raise ValueError('记录被截断')
    return struct.unpack_from('<I', data, pos)[0]


def read_point(data):
    candidates = []
    # 飞龙顶拟建监控塔 26 contains attachment metadata before its coordinates.
    # Search only inside the declared object frame and require the entire
    # UTF-8 name/description tail to end exactly at that object's boundary.
    for pos in range(72, len(data)-36):
        lat, lng = struct.unpack_from('<dd', data, pos)
        if not (math.isfinite(lat) and math.isfinite(lng) and -90<=lat<=90 and -180<=lng<=180):
            continue
        if data[pos+16:pos+20] != b'\0'*4:
            continue
        length = data[pos+31]
        end = pos+32+length
        if not length or end+5 > len(data) or data[end] != 0:
            continue
        desc_len = u32(data, end+1)
        tail=end+5+desc_len
        attachment_terminator=(u32(data,72)==105 and tail==len(data)-1 and data[tail:]==b'\0')
        if tail != len(data) and not attachment_terminator:
            continue
        try:
            name = data[pos+32:end].decode('utf-8')
            description = data[end+5:tail].decode('utf-8')
        except UnicodeError:
            continue
        if not name.strip() or any(ord(c)<32 for c in name):
            continue
        candidates.append(dict(name=name,description=description,longitude=lng,latitude=lat,
                               coordinate_offset=pos))
    if len(candidates) != 1:
        raise ValueError(f'点对象坐标/名称不能唯一解码：{len(candidates)} 个候选')
    return candidates[0]


def read_ovobj(path):
    data = path.read_bytes()
    if len(data)<264 or data[:4]!=b'OviO' or u32(data,12)!=105:
        raise ValueError(f'{path.name}：不是已核验的 OviO v105 文件')
    if u32(data,24)!=len(data):
        raise ValueError(f'{path.name}：文件长度与头部声明不一致')
    pos, points, stack = 264, [], []
    while pos<len(data):
        while stack and stack[-1]==0:
            stack.pop()
        if stack:
            stack[-1]-=1
        size=u32(data,pos)+8
        if size<100 or pos+size>len(data) or u32(data,pos+4)!=31:
            raise ValueError(f'{path.name}：对象边界异常 @{pos}')
        frame=data[pos:pos+size]
        kind=u32(frame,28)
        if kind==30:
            stack.append(u32(frame,88))
        elif kind==7:
            point=read_point(frame)
            point['record_offset']=pos
            points.append(point)
        else:
            raise ValueError(f'{path.name}：不支持的对象类型 {kind}，未静默跳过')
        pos+=size
    if any(stack) or not points:
        raise ValueError(f'{path.name}：文件夹子对象计数不一致或没有点')
    return points


def convert(existing, planned, output, audit_path):
    features, audit = [], []
    for kind,sources in (('existing',existing),('planned',planned)):
        for source in sources:
            points=read_ovobj(source)
            source_id=hashlib.sha256(source.name.encode('utf8')).hexdigest()[:10]
            for index,point in enumerate(points,1):
                if not (110<=point['longitude']<=116 and 32<=point['latitude']<=37):
                    raise ValueError(f'{source.name}：点位超出河南周边，需核实坐标，未自动转换')
                features.append({
                    'type':'Feature','id':f'{kind}-{source_id}-{index}',
                    'geometry':{'type':'Point','coordinates':[point['longitude'],point['latitude']]},
                    'properties':{'name':point['name'],'kind':kind,'source':source.name,
                                  'source_description':point['description']},
                })
            audit.append({'source':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                          'kind':kind,'count':len(points),'points':points})
    payload={'type':'FeatureCollection',
             'metadata':{'raw_coordinates_preserved':True,
                         'coordinate_note':'保留附件原始经纬度，未做坐标偏移转换；坐标系尚待来源方确认。'},
             'features':features}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    audit_path.parent.mkdir(parents=True,exist_ok=True)
    audit_path.write_text(json.dumps({'sources':audit,'counts':{
        kind:sum(f['properties']['kind']==kind for f in features) for kind in ('existing','planned')}},
        ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'counts':{a['source']:a['count'] for a in audit},'total':len(features)},ensure_ascii=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--existing',nargs='+',type=Path,required=True)
    p.add_argument('--planned',nargs='+',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path('app_monitor/static/app_monitor/geo/monitoring_towers.geojson'))
    p.add_argument('--audit',type=Path,default=Path('docs/monitoring_validation/tower-import-audit.json'))
    a=p.parse_args()
    convert(a.existing,a.planned,a.output,a.audit)
