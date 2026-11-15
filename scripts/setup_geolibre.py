"""Build the pinned GeoLibre browser app for the local Fangzhou workbench.

Requires Git, Python and Node.js 22+.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'var/geolibre/source'
DIST = ROOT / 'var/geolibre/dist'
COMMIT = '2a0df8c5f1542ef2d577f0fdc038df45a910da8a'
VERSION = '3.7.0'


def install_processing_runtime():
    """Package the upstream processing runtime alongside this installation."""
    python = ROOT / ('var/geolibre/venv/Scripts/python.exe' if os.name == 'nt'
                     else 'var/geolibre/venv/bin/python')
    if not python.is_file():
        subprocess.run([sys.executable, '-m', 'venv', str(python.parents[1])], check=True)
    package = str(SOURCE / 'backend/geolibre_server') + '[vector,raster,conversion,whitebox,obia]'
    subprocess.run([str(python), '-m', 'pip', 'install', '-e', package, 'scipy'], check=True)


def run(*args, cwd=SOURCE, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True)


def build_agent_geometry(npm):
    entry = SOURCE / 'apps/geolibre-desktop/src/ark-agent-geometry.js'
    shutil.copy2(ROOT / 'integrations/geolibre/ark-agent-geometry.js', entry)
    run(npm, 'exec', '--', 'esbuild', str(entry), '--bundle', '--minify',
        '--legal-comments=eof', f'--outfile={DIST / "ark-agent-geometry.js"}')


def install_print_layout_menu():
    # Both entries use the upstream editor and the same project-level printLayout.
    changes = {
        'TopToolbar.tsx': [
            ('import type { ProjectFileActions } from "../../hooks/useProjectFileActions";',
             'import type { ProjectFileActions } from "../../hooks/useProjectFileActions";\nimport { registerArkProjectBuilder } from "../../ark-bridge";'),
            ('  DEFAULT_PROJECT_NAME,\n', '  DEFAULT_PROJECT_NAME,\n  createDefaultPrintLayout,\n  isDefaultPrintLayout,\n'),
            ('import { useMemo, useRef, useState } from "react";',
             'import { useEffect, useMemo, useRef, useState } from "react";'),
            ('  const projectGeneration = useAppStore((s) => s.projectGeneration);',
             '''  const projectGeneration = useAppStore((s) => s.projectGeneration);
  const [printLayoutVersion, setPrintLayoutVersion] = useState(0);
  const startNewPrintLayout = () => {
    const state = useAppStore.getState();
    if (!isDefaultPrintLayout(state.printLayout) &&
        !window.confirm("新建布局会替换当前工程的打印版式，确定新建吗？")) return;
    state.setPrintLayout(createDefaultPrintLayout());
    setPrintLayoutVersion((version) => version + 1);
    dialogs.setPrintLayoutOpen(true);
  };'''),
            ('  const dialogs = useToolbarDialogs();',
             '''  const dialogs = useToolbarDialogs();
  useEffect(() => {
    registerArkProjectBuilder(projectFiles.buildEmbeddedProject);
    return () => registerArkProjectBuilder(null);
  }, [projectFiles.buildEmbeddedProject]);
  useEffect(() => {
    window.parent.postMessage({
      source: "ark-workbench-map", type: "print-layout", open: dialogs.printLayoutOpen,
    }, location.origin);
  }, [dialogs.printLayoutOpen]);'''),
            ('          onPrintLayout={() => dialogs.setPrintLayoutOpen(true)}',
             '          onNewPrintLayout={startNewPrintLayout}\n          onPrintLayout={() => dialogs.setPrintLayoutOpen(true)}'),
            ('key={`print-layout-${projectGeneration}`}', 'key={`print-layout-${projectGeneration}-${printLayoutVersion}`}'),
        ],
        'toolbar/ProjectMenu.tsx': [
            ('  onPrintLayout: () => void;', '  onNewPrintLayout: () => void;\n  onPrintLayout: () => void;'),
            ('  onPrintLayout,', '  onNewPrintLayout,\n  onPrintLayout,'),
            ('        {showPrintGroup && <DropdownMenuSeparator />}',
             '''        {showPrintGroup && <DropdownMenuSeparator />}
        {show("project.printLayout") && (
          <DropdownMenuItem
            onSelect={onNewPrintLayout}
            disabled={!exportImageCapability.granted}
            aria-describedby={exportImageDeniedBy}
          >
            <Printer className="me-2 h-3.5 w-3.5" />
            新建布局…
          </DropdownMenuItem>
        )}'''),
        ],
    }
    for filename, replacements in changes.items():
        relative = 'apps/geolibre-desktop/src/components/layout/' + filename
        source = subprocess.check_output(['git', 'show', f'{COMMIT}:{relative}'], cwd=SOURCE).decode('utf-8')
        for before, after in replacements:
            if source.count(before) != 1:
                raise SystemExit(f'Unexpected print layout integration point in {filename}')
            source = source.replace(before, after, 1)
        (SOURCE / relative).write_text(source, encoding='utf-8')


def install_branding():
    app = SOURCE / 'apps/geolibre-desktop/src'
    for name in ('ark-bridge.ts', 'ark-basemap-presets.tsx'):
        shutil.copy2(ROOT / 'integrations/geolibre' / name, app / name)
    obsolete = app / 'ark-background-layer.tsx'
    if obsolete.is_file():
        obsolete.unlink()
    main_file = app / 'main.tsx'
    original = main_file.read_text(encoding='utf-8').replace('import "./ark-bridge";\n', '')
    marker = 'import "./lib/crypto-random-uuid-polyfill";'
    if marker not in original:
        raise SystemExit('Unexpected upstream entry point')
    main_file.write_text(original.replace(marker, marker + '\nimport "./ark-bridge";', 1), encoding='utf-8')
    # Keep the native Background row and its dialog. Only add provider presets.
    for name in ('LayerPanel.tsx', 'BasemapPickerDialog.tsx'):
        relative = 'apps/geolibre-desktop/src/components/panels/' + name
        original = subprocess.check_output(['git', 'show', f'{COMMIT}:{relative}'], cwd=SOURCE).decode('utf-8')
        if name == 'BasemapPickerDialog.tsx':
            original = 'import { ArkBasemapPresets, arkBasemapChoice } from "../../ark-basemap-presets";\n' + original
            marker = '  const activeChoice = useMemo(() => {\n'
            if original.count(marker) != 1:
                raise SystemExit('Unexpected upstream basemap choice integration point')
            original = original.replace(marker, marker + '    const ark = arkBasemapChoice(basemapStyleUrl);\n    if (ark) return "ark-" + ark;\n', 1)
            marker = '<form className="space-y-5" onSubmit={applyCustom}>\n'
            if original.count(marker) != 1:
                raise SystemExit('Unexpected upstream basemap preset integration point')
            original = original.replace(marker, marker + '          <ArkBasemapPresets onSelect={() => onOpenChange(false)} />\n', 1)
        (SOURCE / relative).write_text(original, encoding='utf-8')
    install_print_layout_menu()
    install_native_assistant()


def install_native_assistant():
    # Keep the upstream processing executor, but do not give the model arbitrary
    # code, external URLs or destructive layer removal as automatic tools.
    shutil.copy2(ROOT / 'integrations/geolibre/ark-server-whitebox.ts',
                 SOURCE / 'apps/geolibre-desktop/src/lib/scripting/ark-server-whitebox.ts')
    relative = 'packages/map/src/index.ts'
    source = subprocess.check_output(['git', 'show', f'{COMMIT}:{relative}'], cwd=SOURCE).decode('utf-8')
    marker = 'export { imageBlobToDataUrl, isFullViewportMapCanvas } from "./map-capture";'
    if source.count(marker) != 1:
        raise SystemExit('Unexpected upstream map capture exports')
    (SOURCE / relative).write_text(source.replace(
        marker, 'export { compositeMapCanvas, imageBlobToDataUrl, isFullViewportMapCanvas } from "./map-capture";'
    ), encoding='utf-8')
    relative = 'apps/geolibre-desktop/src/lib/assistant/agent.ts'
    source = subprocess.check_output(['git', 'show', f'{COMMIT}:{relative}'], cwd=SOURCE).decode('utf-8')
    marker = '      input: unknown;'
    if source.count(marker) != 1:
        raise SystemExit('Unexpected upstream assistant event schema')
    source = source.replace(marker, marker + '\n      callId?: string;\n      phase?: "running";')
    marker = '        // A tool finished — surface it (with any error) in the transcript.'
    if source.count(marker) != 1:
        raise SystemExit('Unexpected upstream assistant event stream')
    source = source.replace(marker, '''        if (event.type === "beforeToolCallEvent") {
          yield { type: "tool", phase: "running", callId: event.toolUse.toolUseId,
            name: event.toolUse.name, input: event.toolUse.input };
          continue;
        }
''' + marker)
    source = source.replace('            error: event.error?.message,',
                            '            error: event.error?.message,\n            callId: event.toolUse.toolUseId,')
    (SOURCE / relative).write_text(source, encoding='utf-8')
    relative = 'apps/geolibre-desktop/src/components/panels/AssistantPanel.tsx'
    source = subprocess.check_output(['git', 'show', f'{COMMIT}:{relative}'], cwd=SOURCE).decode('utf-8')
    marker = '          const label = describeTool(event.name, event.input);'
    if source.count(marker) != 1:
        raise SystemExit('Unexpected upstream assistant transcript')
    (SOURCE / relative).write_text(source.replace(marker, '          if (event.phase === "running") continue;\n' + marker), encoding='utf-8')
    relative = 'apps/geolibre-desktop/src/lib/scripting/scriptingApi.ts'
    source = subprocess.check_output(['git', 'show', f'{COMMIT}:{relative}'], cwd=SOURCE).decode('utf-8')
    source = 'import { runArkWhitebox } from "./ark-server-whitebox";\n' + source
    source = source.replace('  fetchRemoteWhiteboxCatalogSnapshot,', '  fetchWhiteboxTools,')
    source = source.replace('    fetchRemoteWhiteboxCatalogSnapshot(),', '    fetchWhiteboxTools(),')
    before = 'typeof item === "string" ? layers.find((layer) => layer.id === item) : undefined,'
    after = '''typeof item === "string" ? (layers.find((layer) => layer.id === item) ??
            (layers.filter((layer) => layer.name === item).length === 1
              ? layers.find((layer) => layer.name === item) : undefined)) : undefined,'''
    if source.count(before) != 1:
        raise SystemExit('Unexpected upstream Whitebox layer lookup')
    source = source.replace(before, after)
    before = 'async function whiteboxTools(): Promise<WhiteboxTool[]> {'
    after = '''let arkWhiteboxCatalog: Promise<WhiteboxTool[]> | undefined;
async function whiteboxTools(): Promise<WhiteboxTool[]> {
  arkWhiteboxCatalog ??= loadWhiteboxTools().catch((error) => { arkWhiteboxCatalog = undefined; throw error; });
  return arkWhiteboxCatalog;
}
async function loadWhiteboxTools(): Promise<WhiteboxTool[]> {'''
    if source.count(before) != 1:
        raise SystemExit('Unexpected upstream Whitebox catalogue point')
    source = source.replace(before, after)
    before = '        const job = await runWhiteboxToolWasm({'
    after = '        const run = tool.source === "geolibre" ? runWhiteboxToolWasm : runArkWhitebox;\n        const job = await run({'
    if source.count(before) != 1:
        raise SystemExit('Unexpected upstream Whitebox executor point')
    (SOURCE / relative).write_text(source.replace(before, after), encoding='utf-8')
    relative = 'apps/geolibre-desktop/src/components/layout/DesktopShell.tsx'
    source = subprocess.check_output(['git', 'show', f'{COMMIT}:{relative}'], cwd=SOURCE).decode('utf-8')
    before = '  const mapControllerRef = useRef<MapEngine | null>(null);'
    after = before + '\n  useEffect(() => { setArkMapController(() => mapControllerRef.current); return () => setArkMapController(() => null); }, []);'
    if source.count(before) != 1:
        raise SystemExit('Unexpected upstream map controller integration point')
    source = 'import { setArkMapController } from "../../ark-bridge";\n' + source.replace(before, after)
    (SOURCE / relative).write_text(source, encoding='utf-8')
    relative = 'apps/geolibre-desktop/src/lib/assistant/tools.ts'
    source = subprocess.check_output(['git', 'show', f'{COMMIT}:{relative}'], cwd=SOURCE).decode('utf-8')
    before = '  ] as Tool[];\n}'
    after = '''  ] .filter((item) => !["run_python", "run_maplibre_js", "remove_layer", "add_layer_from_url", "add_tile_layer", "web_search", "search_stac", "add_stac_layer"].includes(item.name)) as Tool[];
}'''
    if source.count(before) != 1:
        raise SystemExit('Unexpected upstream assistant tool integration point')
    (SOURCE / relative).write_text(source.replace(before, after), encoding='utf-8')
    relative = 'packages/processing/src/sidecar-client.ts'
    source = subprocess.check_output(['git', 'show', f'{COMMIT}:{relative}'], cwd=SOURCE).decode('utf-8')
    before = '  if (!sidecarAuthToken) return fetchImpl(input, init);'
    after = '''  if (!sidecarAuthToken) {
    const headers = new Headers(init?.headers);
    const csrf = document.cookie.split("; ").find((part) => part.startsWith("csrftoken="))?.slice(10);
    if (csrf) headers.set("X-CSRFToken", decodeURIComponent(csrf));
    return fetchImpl(input, {...init, headers});
  }'''
    if source.count(before) != 1:
        raise SystemExit('Unexpected upstream sidecar transport')
    (SOURCE / relative).write_text(source.replace(before, after), encoding='utf-8')
    relative = 'apps/geolibre-desktop/src/lib/assistant/provider.ts'
    source = subprocess.check_output(['git', 'show', f'{COMMIT}:{relative}'], cwd=SOURCE).decode('utf-8')
    source = source.replace('): Record<string, null> {\n  const headers: Record<string, null> = {};',
                            '): Record<string, string | null> {\n  const headers: Record<string, string | null> = {};')
    before = '  if (suppressAuthorizationHeader) headers.Authorization = null;'
    after = '''  if (suppressAuthorizationHeader) {
    headers.Authorization = null;
    const csrf = document.cookie.split("; ").find((part) => part.startsWith("csrftoken="))?.slice(10);
    if (csrf) headers["X-CSRFToken"] = decodeURIComponent(csrf);
  }'''
    if source.count(before) != 1:
        raise SystemExit('Unexpected upstream assistant authentication point')
    source = source.replace(before, after)
    before = '    result.OPENAI_COMPATIBLE_BASE_URL = managedProxyBaseUrl(proxyUrl, baseOrigin);'
    after = before + '''
    result.GEOLIBRE_AI_PROXY_BASE_URL = result.OPENAI_COMPATIBLE_BASE_URL;
    result.GEOLIBRE_AI_PROXY_OMIT_AUTHORIZATION = "1";'''
    if source.count(before) != 1:
        raise SystemExit('Unexpected upstream assistant proxy point')
    (SOURCE / relative).write_text(source.replace(before, after), encoding='utf-8')


def main():
    npm = shutil.which('npm.cmd') or shutil.which('npm')
    if not npm or not shutil.which('git'):
        raise SystemExit('Install Git and Node.js 22+ before building GeoLibre.')
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    if not SOURCE.exists():
        run('git', 'clone', '--depth', '1', '--branch', 'v' + VERSION, '--filter=blob:none',
            'https://github.com/opengeos/GeoLibre.git', str(SOURCE), cwd=ROOT)
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip()
    if actual != COMMIT:
        raise SystemExit('GeoLibre source does not match the pinned commit. Use a separate matching source checkout.')
    install_processing_runtime()
    install_branding()
    run(npm, 'ci', '--no-audit', '--no-fund')
    run(npm, 'run', 'build', '-w', '@geolibre/embed')
    env = os.environ.copy()
    # Relative assets make this build usable below /workbench/geolibre/ and /platform/.
    env.update(GEOLIBRE_EMBED='1', GEOLIBRE_APP_BASE='./', VITE_WELCOME_DISABLED='1',
               VITE_GEOLIBRE_APP_NAME='ARK GeoStudio', GEOLIBRE_DUCKDB_WASM_CDN='1',
               VITE_GEOLIBRE_AI_URL='/workbench/agent/native', VITE_GEOLIBRE_AI_MODEL='deepseek-chat',
               NODE_OPTIONS='--max-old-space-size=6144')
    if not DIST.resolve().is_relative_to((ROOT / 'var/geolibre').resolve()):
        raise SystemExit('Unexpected output path')
    run(npm, 'exec', '--', 'vite', 'build', '--outDir', str(DIST),
        cwd=SOURCE / 'apps/geolibre-desktop', env=env)
    build_agent_geometry(npm)
    target = ROOT / 'app_monitor/static/app_monitor/workbench'
    shutil.copy2(SOURCE / 'packages/embed/dist/index.js', target / 'geolibre-embed.js')
    shutil.copy2(SOURCE / 'LICENSE', target / 'GEOLIBRE-LICENSE.txt')
    shutil.copy2(SOURCE / 'LICENSE', DIST / 'GEOLIBRE-LICENSE.txt')
    (DIST / '.build-info.json').write_text(json.dumps({'version': VERSION, 'commit': COMMIT,
                                                    'embedded': True, 'base': './'}), encoding='utf-8')
    print('GeoLibre ' + VERSION + ' ready. Open http://127.0.0.1:8012/workbench/')


if __name__ == '__main__':
    main()
