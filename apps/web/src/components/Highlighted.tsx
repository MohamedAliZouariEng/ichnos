/** Render a search snippet, turning «matches» into <mark> without using HTML from the API. */
export function Highlighted({ snippet }: { snippet: string }) {
  const parts = snippet.split(/(«[^»]*»)/g).filter(Boolean);
  return (
    <>
      {parts.map((part, index) =>
        part.startsWith("«") && part.endsWith("»") ? (
          <mark key={index}>{part.slice(1, -1)}</mark>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}
