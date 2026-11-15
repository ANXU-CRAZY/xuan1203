import buffer from '@turf/buffer';
import booleanPointInPolygon from '@turf/boolean-point-in-polygon';
import {
    centroidsTool, convexHullTool, boundingBoxTool, dissolveTool, explodeTool, smoothTool,
    extractVerticesTool, clipTool, intersectionTool, differenceTool, unionTool,
} from '../../../packages/processing/src/vector-tools';

const vectorTools = {
    centroids: centroidsTool, convex_hull: convexHullTool, bounding_box: boundingBoxTool,
    dissolve: dissolveTool, explode: explodeTool, smooth: smoothTool, extract_vertices: extractVerticesTool,
    clip: clipTool, intersection: intersectionTool, difference: differenceTool, union: unionTool,
};

function limit(features) {
    if (features.length > 2000) throw new Error('单个分析图层最多支持 2000 个要素。');
    let vertices = 0;
    function visit(value, depth = 0) {
        if (!Array.isArray(value) || depth > 5) throw new Error('图层包含无法处理的坐标。');
        if (typeof value[0] === 'number') {
            const [lng, lat] = value;
            if (!Number.isFinite(lng) || !Number.isFinite(lat) || Math.abs(lng) > 180 || Math.abs(lat) > 90) {
                throw new Error('分析需要有效的 WGS84 经纬度。');
            }
            if (++vertices > 30000) throw new Error('单个分析图层最多支持 30000 个坐标。');
        } else {
            for (const part of value) visit(part, depth + 1);
        }
    }
    for (const feature of features) visit(feature.geometry?.coordinates);
    return vertices;
}

function interpolate(points, field) {
    if (points.length < 2 || points.some(point => point.geometry?.type !== 'Point')) {
        throw new Error('IDW 插值需要至少两个点要素。');
    }
    const samples = points.map(point => ({
        x: point.geometry.coordinates[0], y: point.geometry.coordinates[1], value: point.properties?.[field],
    })).filter(point => typeof point.value === 'number' && Number.isFinite(point.value));
    if (samples.length < 2) throw new Error('所选字段至少需要两个有效数值。');
    const west = Math.min(...samples.map(point => point.x));
    const east = Math.max(...samples.map(point => point.x));
    const south = Math.min(...samples.map(point => point.y));
    const north = Math.max(...samples.map(point => point.y));
    if (east === west || north === south || east - west > 180 || north > 85 || south < -85) {
        throw new Error('点的范围无法生成网格，请检查坐标和空间范围。');
    }
    const low = Math.min(...samples.map(point => point.value));
    const high = Math.max(...samples.map(point => point.value));
    const colors = ['#296c94', '#52a5b3', '#a8d5af', '#f3d382', '#dc7951'];
    const cols = 32;
    const rows = 32;
    const dx = (east - west) / cols;
    const dy = (north - south) / rows;
    const radians = Math.PI / 180;
    const cells = [];
    for (let row = 0; row < rows; row++) {
        const y = south + (row + .5) * dy;
        for (let col = 0; col < cols; col++) {
            const x = west + (col + .5) * dx;
            let sum = 0, weights = 0, exactSum = 0, exactCount = 0;
            for (const sample of samples) {
                const deltaLat = (sample.y - y) * radians;
                const deltaLon = (sample.x - x) * radians;
                const a = Math.sin(deltaLat / 2) ** 2 +
                    Math.cos(y * radians) * Math.cos(sample.y * radians) * Math.sin(deltaLon / 2) ** 2;
                const distance = 2 * 6371008.8 * Math.asin(Math.min(1, Math.sqrt(a)));
                if (distance < 0.001) { exactSum += sample.value; exactCount++; continue; }
                const weight = 1 / (distance * distance);
                sum += weight * sample.value;
                weights += weight;
            }
            const value = exactCount ? exactSum / exactCount : sum / weights;
            const band = high === low ? 2 : Math.min(4, Math.floor((value - low) / (high - low) * 5));
            const x0 = west + col * dx, x1 = west + (col + 1) * dx;
            const y0 = south + row * dy, y1 = south + (row + 1) * dy;
            cells.push({type: 'Feature', geometry: {type: 'Polygon', coordinates: [[
                [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0],
            ]]}, properties: {'插值': value, fill: colors[band], 'fill-opacity': .72, 'stroke-opacity': 0}});
        }
    }
    return {features: cells, meta: {field, sampleCount: samples.length, skipped: points.length - samples.length,
        min: low, max: high, power: 2, columns: cols, rows}};
}

self.onmessage = ({data: {tool, features, meters, areas, field}}) => {
    try {
        limit(features);
        let result;
        if (tool === 'buffer') {
            result = features.map(feature => {
                const polygon = buffer(
                    {type: 'Feature', geometry: feature.geometry, properties: {}},
                    meters, {units: 'meters', steps: 12},
                );
                if (!polygon?.geometry) throw new Error('部分要素无法生成缓冲面，请检查原图层。');
                return {type: 'Feature', geometry: polygon.geometry, properties: {buffer_m: meters}};
            });
            limit(result);
        } else if (tool === 'points_within') {
            if (!features.every(feature => feature.geometry?.type === 'Point') ||
                !areas.length || !areas.every(feature => ['Polygon', 'MultiPolygon'].includes(feature.geometry?.type))) {
                throw new Error('空间筛选需要点图层和有效的面图层。');
            }
            if (limit(areas) * features.length > 10_000_000) throw new Error('点面筛选范围过大，请先缩小图层规模。');
            result = features.filter(feature => areas.some(area => booleanPointInPolygon(feature, area)));
        } else if (tool === 'idw') {
            self.postMessage(interpolate(features, field));
            return;
        } else if (Object.hasOwn(vectorTools, tool)) {
            if (areas?.length) {
                limit(areas);
                if (features.length * areas.length > 250000) throw new Error('图层规模过大，请先缩小分析范围。');
            }
            let output;
            const log = [];
            vectorTools[tool].run({
                layers: [
                    {id: 'input', geojson: {type: 'FeatureCollection', features}},
                    {id: 'overlay', geojson: {type: 'FeatureCollection', features: areas || []}},
                ],
                parameters: {layer: 'input', overlay: 'overlay'},
                log: message => log.push(message),
                addResultLayer: (_name, collection) => { output = collection.features; },
            });
            if (!output) throw new Error('分析未生成结果，请检查图层几何类型。');
            limit(output);
            result = output;
        } else {
            throw new Error('该空间分析尚未支持。');
        }
        self.postMessage({features: result});
    } catch (error) {
        const detail = error instanceof Error && /[\u4e00-\u9fff]/.test(error.message)
            ? error.message : '空间分析失败，请检查图层几何。';
        self.postMessage({detail});
    }
};
