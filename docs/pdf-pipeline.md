# PDF pipeline

PDF assets are processed by the original Marker-based parser. Marker emits structured JSON blocks; block parsers normalize sections, tables, lists, and other content. The parser carries section context across pages and uses Chonkie SentenceChunker with the configured token size and overlap. Each resulting LangChain Document retains page and bounding-box citation metadata. The original OpenAI embedding helper generates vectors, which are written to the Weaviate PDF collection with asset scoping.
