"use client";

import { useEffect, useId, useRef } from "react";
import type { KeyboardEvent } from "react";
import type { MetadataSearchColumnSummary, MetadataSearchTableSummary } from "@/lib/api/types";

const DESCRIPTION_FALLBACK = "설명 없음";

function displayText(value?: string | null): string {
  const text = value?.trim();
  return text ? text : DESCRIPTION_FALLBACK;
}

function focusableElements(container: HTMLElement | null): HTMLElement[] {
  if (!container) {
    return [];
  }
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute("disabled") && element.tabIndex !== -1);
}

export function MetadataTableDetailModal({
  table,
  columns,
  onClose,
}: Readonly<{
  table: MetadataSearchTableSummary;
  columns: MetadataSearchColumnSummary[];
  onClose: () => void;
}>) {
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();
    return () => {
      previousFocus?.focus();
    };
  }, []);

  function onDialogKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") {
      return;
    }
    const focusable = focusableElements(dialogRef.current);
    if (focusable.length === 0) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      className="metadata-modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section
        ref={dialogRef}
        aria-labelledby={titleId}
        aria-modal="true"
        className="metadata-table-modal"
        onKeyDown={onDialogKeyDown}
        role="dialog"
        tabIndex={-1}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">테이블 상세</p>
            <h2 id={titleId}>{table.name}</h2>
            <p className="metadata-result-description">{displayText(table.description)}</p>
          </div>
          <button ref={closeButtonRef} className="secondary-action" type="button" onClick={onClose}>
            닫기
          </button>
        </div>

        <div className="data-table-wrap">
          <table className="data-table metadata-field-table">
            <thead>
              <tr>
                <th scope="col">필드명</th>
                <th scope="col">필드 디스크립션</th>
                <th scope="col">타입</th>
              </tr>
            </thead>
            <tbody>
              {columns.length > 0 ? (
                columns.map((column) => (
                  <tr key={column.name}>
                    <td>{column.name}</td>
                    <td>{displayText(column.description)}</td>
                    <td>{displayText(column.dataType)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={3}>상세 필드 정보 없음</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
