export interface AnnotationToolDefinition {
  id: string
  label: string
  shortcut: string
}

export const ANNOTATION_TOOLS: readonly AnnotationToolDefinition[] = [
  { id: 'pan', label: 'Pan', shortcut: 'H' },
  { id: 'select', label: 'Select', shortcut: 'V' },
  { id: 'marquee', label: 'Marquee', shortcut: 'M' },
  { id: 'point', label: 'Point', shortcut: 'P' },
  { id: 'ruler', label: 'Ruler', shortcut: 'R' },
  { id: 'polyline', label: 'Polyline', shortcut: 'L' },
  { id: 'angle', label: 'Angle', shortcut: 'A' },
  { id: 'rectangle', label: 'Rectangle', shortcut: 'B' },
  { id: 'ellipse', label: 'Ellipse', shortcut: 'E' },
  { id: 'polygon', label: 'Polygon', shortcut: 'G' },
  { id: 'freehand', label: 'Freehand', shortcut: 'F' },
  { id: 'brush-add', label: 'Brush add', shortcut: ']' },
  { id: 'brush-subtract', label: 'Brush subtract', shortcut: '[' },
  { id: 'text', label: 'Text', shortcut: 'T' },
] as const

export function AnnotationToolbar({
  activeTool,
  onTool,
}: {
  activeTool: string
  onTool: (tool: string) => void
}) {
  return (
    <div className="pathlab-annotation-toolbar" role="toolbar" aria-label="Annotation tools">
      {ANNOTATION_TOOLS.map((tool) => (
        <button
          key={tool.id}
          type="button"
          className={tool.id === activeTool ? 'active' : undefined}
          aria-pressed={tool.id === activeTool}
          title={`${tool.label} (${tool.shortcut})`}
          onClick={() => onTool(tool.id)}
        >
          <span>{tool.label}</span>
          <kbd>{tool.shortcut}</kbd>
        </button>
      ))}
    </div>
  )
}
