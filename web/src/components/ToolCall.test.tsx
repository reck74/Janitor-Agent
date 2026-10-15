import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ToolCall, type ToolEntry } from "./ToolCall";

const base: ToolEntry = {
  kind: "tool", id: "entry", tool_id: "call", name: "apply_patch",
  status: "done", startedAt: 0,
};

describe("tool details remain reachable", () => {
  it("disables expansion only when no details exist", () => {
    expect(renderToStaticMarkup(<ToolCall tool={base} />)).toContain('disabled=""');
    for (const detail of ["context", "preview", "summary", "error", "inline_diff"] as const) {
      const html = renderToStaticMarkup(<ToolCall tool={{ ...base, [detail]: "details" }} />);
      expect(html).not.toContain('disabled=""');
    }
  });

  it("expands an error with its diff and hides unknown historical timing", () => {
    const html = renderToStaticMarkup(<ToolCall tool={{ ...base, status: "error", error: "failed", inline_diff: "+added" }} />);
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain("+added");
    expect(html).toContain("failed");
    expect(html).not.toContain("0ms");
  });
});
