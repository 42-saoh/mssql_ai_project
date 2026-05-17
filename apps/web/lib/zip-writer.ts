export interface ZipEntry {
  name: string;
  content: string;
}

const textEncoder = new TextEncoder();
const crcTable = new Uint32Array(256);

for (let index = 0; index < 256; index += 1) {
  let value = index;
  for (let bit = 0; bit < 8; bit += 1) {
    value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  }
  crcTable[index] = value >>> 0;
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function dosDateTime(date: Date): { date: number; time: number } {
  const year = Math.max(date.getFullYear(), 1980);
  return {
    date: ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate(),
    time: (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2),
  };
}

function uint16(value: number): Uint8Array {
  return Uint8Array.of(value & 0xff, (value >>> 8) & 0xff);
}

function uint32(value: number): Uint8Array {
  return Uint8Array.of(
    value & 0xff,
    (value >>> 8) & 0xff,
    (value >>> 16) & 0xff,
    (value >>> 24) & 0xff,
  );
}

function concat(parts: Uint8Array[]): Uint8Array {
  const totalLength = parts.reduce((sum, part) => sum + part.length, 0);
  const output = new Uint8Array(totalLength);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
}

export function createStoreOnlyZip(entries: ZipEntry[], now = new Date()): Uint8Array {
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  const { date, time } = dosDateTime(now);
  let offset = 0;

  for (const entry of entries) {
    const nameBytes = textEncoder.encode(entry.name);
    const contentBytes = textEncoder.encode(entry.content);
    const checksum = crc32(contentBytes);
    const localHeader = concat([
      uint32(0x04034b50),
      uint16(20),
      uint16(0x0800),
      uint16(0),
      uint16(time),
      uint16(date),
      uint32(checksum),
      uint32(contentBytes.length),
      uint32(contentBytes.length),
      uint16(nameBytes.length),
      uint16(0),
      nameBytes,
    ]);
    localParts.push(localHeader, contentBytes);

    centralParts.push(
      concat([
        uint32(0x02014b50),
        uint16(20),
        uint16(20),
        uint16(0x0800),
        uint16(0),
        uint16(time),
        uint16(date),
        uint32(checksum),
        uint32(contentBytes.length),
        uint32(contentBytes.length),
        uint16(nameBytes.length),
        uint16(0),
        uint16(0),
        uint16(0),
        uint16(0),
        uint32(0),
        uint32(offset),
        nameBytes,
      ]),
    );
    offset += localHeader.length + contentBytes.length;
  }

  const centralDirectory = concat(centralParts);
  const endOfCentralDirectory = concat([
    uint32(0x06054b50),
    uint16(0),
    uint16(0),
    uint16(entries.length),
    uint16(entries.length),
    uint32(centralDirectory.length),
    uint32(offset),
    uint16(0),
  ]);

  return concat([...localParts, centralDirectory, endOfCentralDirectory]);
}
