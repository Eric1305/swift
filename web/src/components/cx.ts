/** Joins truthy class names. */
export default function cx(...names: (string | false | null | undefined)[]): string {
  return names.filter(Boolean).join(' ');
}
