const EDITABLE_KEYBOARD_TAGS = new Set(["INPUT", "TEXTAREA"]);

/** Whether a keyboard event target accepts regular text input. */
export function isEditableKeyboardTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  return Boolean(
    element && (EDITABLE_KEYBOARD_TAGS.has(element.tagName) || element.isContentEditable),
  );
}
