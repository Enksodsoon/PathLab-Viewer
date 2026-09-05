import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, type ComponentPropsWithoutRef } from 'react'

function resizeTextarea(node: HTMLTextAreaElement | null) {
  if (!node) return
  node.style.height = 'auto'
  node.style.height = `${node.scrollHeight}px`
}

export const AutoGrowTextarea = forwardRef<HTMLTextAreaElement, ComponentPropsWithoutRef<'textarea'>>(function AutoGrowTextarea({ onInput, value, ...props }, forwardedRef) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useImperativeHandle(forwardedRef, () => textareaRef.current as HTMLTextAreaElement)
  useLayoutEffect(() => resizeTextarea(textareaRef.current), [value])

  return <textarea
    {...props}
    ref={textareaRef}
    value={value}
    rows={1}
    onInput={(event) => {
      resizeTextarea(event.currentTarget)
      onInput?.(event)
    }}
  />
})
