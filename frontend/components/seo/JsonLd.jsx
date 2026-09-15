// Renders one or more schema.org objects as a JSON-LD script. Server
// component: the block ends up in the exported HTML, which is where a crawler
// reads it. `data` is an object or an array of objects.
//
// The "<" escape keeps a value containing "</script>" from closing the tag
// early; JSON.stringify does not do that on its own.
export default function JsonLd({ data }) {
  const items = Array.isArray(data) ? data : [data];
  return items.map((item, index) => (
    <script
      key={index}
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(item).replace(/</g, "\\u003c") }}
    />
  ));
}
