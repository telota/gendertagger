/**
 * Columns of the tabular person-register profile (CSV/XLSX/JSON), in the order the backend requires;
 * see docs/08-ingestion-and-export.md. The server stays authoritative, this only lets the form say
 * what is expected and catch a wrong header before the upload creates a doomed snapshot.
 */
export const PERSON_REGISTER_COLUMNS = [
  'xml:id',
  'persName',
  'birth',
  'death',
  'event',
  'note',
  'idno',
] as const

const BYTE_ORDER_MARK = String.fromCharCode(0xfeff)
const withoutBom = (text: string): string =>
  text.startsWith(BYTE_ORDER_MARK) ? text.slice(1) : text

// Enough for any sane header row; a file with a longer first line is not this profile anyway.
const HEADER_READ_BYTES = 64 * 1024

/** Read the first line of a CSV file as a list of column names (UTF-8 BOM and quoting removed). */
export async function readCsvHeader(file: Blob): Promise<string[]> {
  const text = await file.slice(0, HEADER_READ_BYTES).text()
  const firstLine = withoutBom(text).split(/\r\n|\n|\r/, 1)[0] ?? ''
  return firstLine.split(',').map((column) => column.trim().replace(/^"(.*)"$/, '$1'))
}

export function isPersonRegisterHeader(header: readonly string[]): boolean {
  return (
    header.length === PERSON_REGISTER_COLUMNS.length &&
    header.every((column, index) => column === PERSON_REGISTER_COLUMNS[index])
  )
}
