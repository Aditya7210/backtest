import { useEffect, useState } from 'react';

interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  height?: number;
  readOnly?: boolean;
}

type MonacoEditorType = (props: {
  value: string;
  onChange: (value: string | undefined) => void;
  language?: string;
  height?: string | number;
  theme?: string;
  options?: Record<string, unknown>;
}) => JSX.Element;

export default function CodeEditor({ value, onChange, height = 640, readOnly = false }: CodeEditorProps) {
  const [MonacoEditor, setMonacoEditor] = useState<MonacoEditorType | null>(null);
  const [monacoTried, setMonacoTried] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        // Runtime-only import so build remains valid even when Monaco dependency is unavailable.
        const dynamicImport = Function('m', 'return import(m)') as (m: string) => Promise<{ default: MonacoEditorType }>;
        const mod = await dynamicImport('@monaco-editor/react');
        if (!active) return;
        setMonacoEditor(() => mod.default);
      } catch {
        if (!active) return;
        setMonacoEditor(null);
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
        theme="vs-light"
        options={{
          readOnly,
          minimap: { enabled: false },
          tabSize: 4,
          wordWrap: 'on',
          fontSize: 13,
          automaticLayout: true,
          scrollBeyondLastLine: false,
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
          Monaco unavailable. Using fallback editor.
        </div>
      )}
      <textarea
        className="input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        readOnly={readOnly}
        style={{ minHeight: height, fontFamily: 'var(--font-mono)', fontSize: '0.82rem', lineHeight: 1.6 }}
      />
    </div>
  );
}
