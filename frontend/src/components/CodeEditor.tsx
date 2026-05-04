import { useEffect, useState } from 'react';
import type { ComponentType } from 'react';

interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  height?: number | string;
  readOnly?: boolean;
}

type MonacoEditorType = ComponentType<{
  value: string;
  onChange: (value: string | undefined) => void;
  language?: string;
  height?: string | number;
  theme?: string;
  beforeMount?: (monaco: any) => void; // eslint-disable-line @typescript-eslint/no-explicit-any
  options?: Record<string, unknown>;
}>;

export default function CodeEditor({ value, onChange, height = 640, readOnly = false }: CodeEditorProps) {
  const [MonacoEditor, setMonacoEditor] = useState<MonacoEditorType | null>(null);
  const [monacoTried, setMonacoTried] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const mod = await import('@monaco-editor/react');
        if (!active) return;
        setMonacoEditor(mod.default as MonacoEditorType);
        setLoadError(null);
      } catch (error: unknown) {
        if (!active) return;
        setMonacoEditor(null);
        setLoadError(error instanceof Error ? error.message : 'Monaco failed to load.');
      } finally {
        if (active) setMonacoTried(true);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, []);

  if (MonacoEditor) {
    return (
      <MonacoEditor
        value={value}
        onChange={(next) => onChange(next ?? '')}
        language="python"
        height={height}
        theme="ue-vscode-light"
        beforeMount={(monaco) => {
          monaco.editor.defineTheme('ue-vscode-light', {
            base: 'vs',
            inherit: true,
            rules: [
              { token: 'keyword', foreground: '7C3AED', fontStyle: 'bold' },
              { token: 'string', foreground: '059669' },
              { token: 'number', foreground: 'C2410C' },
              { token: 'comment', foreground: '94A3B8', fontStyle: 'italic' },
              { token: 'type.identifier', foreground: '2563EB' },
              { token: 'delimiter', foreground: '475569' },
              { token: 'operator', foreground: 'DB2777' },
              { token: 'identifier', foreground: '0F172A' },
            ],
            colors: {
              'editor.background': '#FFFFFF',
              'editor.foreground': '#0F172A',
              'editor.lineHighlightBackground': '#F8FAFC',
              'editorLineNumber.foreground': '#94A3B8',
              'editorLineNumber.activeForeground': '#475569',
              'editorCursor.foreground': '#2563EB',
              'editor.selectionBackground': '#DBEAFE',
              'editor.inactiveSelectionBackground': '#E2E8F0',
              'editorIndentGuide.background1': '#E2E8F0',
              'editorIndentGuide.activeBackground1': '#CBD5E1',
            },
          });
        }}
        options={{
          readOnly,
          minimap: { enabled: false },
          tabSize: 4,
          wordWrap: 'off',
          fontSize: 13.5,
          fontFamily: 'JetBrains Mono, Fira Code, Cascadia Code, monospace',
          automaticLayout: true,
          scrollBeyondLastLine: false,
          renderLineHighlight: 'all',
          glyphMargin: false,
          folding: true,
          bracketPairColorization: { enabled: true },
          guides: { bracketPairs: true, indentation: true },
          overviewRulerBorder: false,
          lineDecorationsWidth: 0,
          padding: { top: 10, bottom: 10 },
          smoothScrolling: true,
        }}
      />
    );
  }

  return (
    <div>
      {!monacoTried ? (
        <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: 6 }}>
          Loading code editor...
        </div>
      ) : (
        <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: 6 }}>
          Monaco unavailable{loadError ? ` (${loadError})` : ''}. Using fallback editor.
        </div>
      )}
      <textarea
        className="input backtest-editor-fallback"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        readOnly={readOnly}
        style={{
          height,
          minHeight: typeof height === 'number' ? `${height}px` : height,
          fontFamily: 'var(--font-mono)',
          fontSize: '0.82rem',
          lineHeight: 1.6,
          resize: 'none',
        }}
      />
    </div>
  );
}
