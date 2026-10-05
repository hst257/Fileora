export function HighlightedText({
  text,
  query,
}: {
  text: string;
  query: string;
}) {
  const terms = [...new Set(query.match(/[\p{L}\p{N}_]{3,}/gu) || [])].filter(
    (term) =>
      !["find", "the", "about", "where", "notes", "files"].includes(
        term.toLowerCase(),
      ),
  );
  if (!terms.length) return <>{text}</>;
  const pattern = new RegExp(
    `(${terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "giu",
  );
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 ? <mark key={index}>{part}</mark> : part,
      )}
    </>
  );
}
