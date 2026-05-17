#!/usr/bin/env node

import assert from "node:assert/strict";
import {
  artifactContentType,
  artifactFileExtension,
  artifactFilename,
  sanitizeFilePart,
} from "../lib/artifact-download.ts";
import { createStoreOnlyZip } from "../lib/zip-writer.ts";

const textDecoder = new TextDecoder();

function readUInt16(buffer, offset) {
  return buffer.readUInt16LE(offset);
}

function readUInt32(buffer, offset) {
  return buffer.readUInt32LE(offset);
}

function findEndOfCentralDirectory(buffer) {
  for (let offset = buffer.length - 22; offset >= 0; offset -= 1) {
    if (readUInt32(buffer, offset) === 0x06054b50) {
      return offset;
    }
  }
  throw new Error("ZIP end of central directory was not found.");
}

function listStoreOnlyZipEntries(zipBytes) {
  const buffer = Buffer.from(zipBytes);
  assert.equal(readUInt32(buffer, 0), 0x04034b50, "ZIP must start with a local header.");

  const eocdOffset = findEndOfCentralDirectory(buffer);
  const entryCount = readUInt16(buffer, eocdOffset + 10);
  const centralOffset = readUInt32(buffer, eocdOffset + 16);
  const entries = new Map();
  let offset = centralOffset;

  for (let index = 0; index < entryCount; index += 1) {
    assert.equal(readUInt32(buffer, offset), 0x02014b50, "Missing central directory header.");
    const compressedSize = readUInt32(buffer, offset + 20);
    const uncompressedSize = readUInt32(buffer, offset + 24);
    const nameLength = readUInt16(buffer, offset + 28);
    const extraLength = readUInt16(buffer, offset + 30);
    const commentLength = readUInt16(buffer, offset + 32);
    const localOffset = readUInt32(buffer, offset + 42);
    const name = buffer.subarray(offset + 46, offset + 46 + nameLength).toString("utf8");

    assert.equal(compressedSize, uncompressedSize, `${name} should be stored, not compressed.`);
    assert.equal(readUInt32(buffer, localOffset), 0x04034b50, `${name} local header missing.`);
    assert.equal(readUInt16(buffer, localOffset + 8), 0, `${name} should use store-only method.`);
    const localNameLength = readUInt16(buffer, localOffset + 26);
    const localExtraLength = readUInt16(buffer, localOffset + 28);
    const contentStart = localOffset + 30 + localNameLength + localExtraLength;
    const content = textDecoder.decode(buffer.subarray(contentStart, contentStart + compressedSize));
    entries.set(name, content);

    offset += 46 + nameLength + extraLength + commentLength;
  }

  return entries;
}

assert.equal(artifactFileExtension("SP_ANALYSIS_DOC"), "md");
assert.equal(artifactFileExtension("DEPENDENCY_REPORT"), "md");
assert.equal(artifactFileExtension("MAPPER_XML"), "xml");
assert.equal(artifactFileExtension("MAPPER_INTERFACE"), "java");
assert.equal(artifactFileExtension("SERVICE_DRAFT"), "java");
assert.equal(artifactFileExtension("DTO_DRAFT"), "java");
assert.equal(artifactFileExtension("VALIDATION_REPORT"), "json");
assert.equal(artifactFileExtension("FUTURE_ARTIFACT_TYPE"), "txt");
assert.equal(artifactContentType("MAPPER_XML"), "application/xml; charset=utf-8");
assert.equal(artifactContentType("SP_ANALYSIS_DOC"), "text/markdown; charset=utf-8");
assert.equal(artifactContentType("FUTURE_ARTIFACT_TYPE"), "text/plain; charset=utf-8");

const sanitized = sanitizeFilePart(" ../dbo.Get Item?.sql ");
assert(!sanitized.includes("/"));
assert(!sanitized.includes("\\"));
assert(!sanitized.includes("?"));
assert(sanitized.length <= 80);
assert.equal(sanitizeFilePart("   "), "draft");

assert.equal(
  artifactFilename(
    {
      artifactId: "art:123/456",
      type: "MAPPER_XML",
      title: "src/main/resources/mybatis/Get Item Mapper.xml",
    },
    2,
  ),
  "02-src-main-resources-mybatis-Get-Item-Mapper.xml-art-123-456.xml",
);

const zip = createStoreOnlyZip(
  [
    { name: "README.md", content: "# Draft artifacts" },
    { name: "manifest.json", content: '{"draftOnly":true}' },
    { name: "01-analysis.md", content: "quality_summary: evidence-bound draft" },
  ],
  new Date("2026-05-17T00:00:00Z"),
);
const entries = listStoreOnlyZipEntries(zip);
assert.deepEqual([...entries.keys()], ["README.md", "manifest.json", "01-analysis.md"]);
assert.equal(entries.get("README.md"), "# Draft artifacts");
assert.equal(entries.get("manifest.json"), '{"draftOnly":true}');
assert.equal(entries.get("01-analysis.md"), "quality_summary: evidence-bound draft");

console.log("draft download helper smoke passed");
