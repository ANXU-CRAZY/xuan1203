import {fetchWhiteboxJob, type WhiteboxJob, type WhiteboxLayerInput, type WhiteboxTool} from '@geolibre/processing';
import {parameterKind} from '../whitebox-param-kind';

type Input = WhiteboxLayerInput | WhiteboxLayerInput[];
type Request = {tool_id: string; parameters: Record<string, unknown>; tool: WhiteboxTool;
    layer_inputs: Record<string, Input>};

/** Execute bundled native Whitebox tools in the platform processing component. */
export async function runArkWhitebox(request: Request): Promise<WhiteboxJob> {
    const body = new FormData();
    const inputs: {name: string; file: string; kind: string}[] = [];
    for (const [name, item] of Object.entries(request.layer_inputs)) {
        for (const layer of Array.isArray(item) ? item : [item]) {
            const file = 'input' + inputs.length;
            const data = layer.kind === 'vector_in' && layer.geojson
                ? new Blob([JSON.stringify(layer.geojson)], {type: 'application/geo+json'})
                : layer.bytes ? new Blob([layer.bytes as BlobPart], {type: 'application/octet-stream'}) : null;
            if (!data) throw new Error('无法读取输入图层数据。');
            body.append(file, data, file);
            inputs.push({name, file, kind: layer.kind});
        }
    }
    const output_kinds = (request.tool.params || []).map(param => {
        let kind = parameterKind(param);
        // Some Whitebox tools describe an output GeoTIFF merely as "file".
        if (kind === 'file_out' && /raster|terrain|hydro/i.test(request.tool.category || '') &&
            /raster|geotiff|\.tiff?|output path/i.test(param.description || '')) kind = 'raster_out';
        return {name: param.name, kind};
    });
    body.append('manifest', JSON.stringify({tool_id: request.tool_id, parameters: request.parameters, inputs, output_kinds}));
    const csrf = document.cookie.split('; ').find(part => part.startsWith('csrftoken='))?.slice(10) || '';
    const response = await fetch('/workbench/analysis/whitebox/', {method: 'POST', body,
        headers: {'X-CSRFToken': decodeURIComponent(csrf)}});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '空间计算任务启动失败。');
    let job = data.job as WhiteboxJob;
    const deadline = Date.now() + 300000;
    while (job.status === 'pending' || job.status === 'running') {
        if (Date.now() > deadline) throw new Error('空间计算超时，任务可能仍在后台运行。');
        await new Promise(resolve => setTimeout(resolve, 700));
        job = await fetchWhiteboxJob(job.id);
    }
    if (job.status !== 'succeeded') return job;
    for (const [index, artifact] of data.artifacts.entries()) {
        const outputName = Object.keys(job.outputs).find(key => job.outputs[key] === artifact.path);
        if (!outputName) continue;
        const output = await fetch(`/workbench/analysis/artifact/${data.directory}/${index}/`);
        if (!output.ok) throw new Error('分析完成，但无法读取输出文件。');
        job.outputs[outputName] = artifact.kind === 'vector_out' ? await output.json() : new Uint8Array(await output.arrayBuffer());
    }
    return job;
}
