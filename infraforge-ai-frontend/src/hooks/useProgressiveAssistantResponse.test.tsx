import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, act } from "@testing-library/react";
import { renderHook } from "@testing-library/react";
import { useProgressiveAssistantResponse } from "./useProgressiveAssistantResponse";
import { RESPONSE_ANIMATION_CONFIG } from "../utils/progressiveResponseConfig";
import ConstructionCraneTextBuilder from "../components/Assistant/ConstructionCraneTextBuilder";
import AssistantMessageContent from "../components/Assistant/AssistantMessageContent";
import LoadingIndicator from "../components/Assistant/LoadingIndicator";

const indexCss = readFileSync(resolve(__dirname, "../index.css"), "utf8");

describe("useProgressiveAssistantResponse", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("reveals text progressively after start", () => {
    const updates: string[] = [];
    const { result } = renderHook(() =>
      useProgressiveAssistantResponse({
        onUpdate: (_id, text) => updates.push(text),
        onComplete: () => {},
      }),
    );

    act(() => {
      result.current.start("m1", "Hello world from InfraForge");
    });

    expect(result.current.isGenerating).toBe(true);
    expect(updates[0]).toBe("");

    act(() => {
      vi.advanceTimersByTime(RESPONSE_ANIMATION_CONFIG.minimumDuration);
    });
    expect(updates.some((text) => text.startsWith("Hello"))).toBe(true);

    act(() => {
      vi.runAllTimers();
    });

    expect(result.current.isGenerating).toBe(false);
    expect(updates[updates.length - 1]).toBe("Hello world from InfraForge");
  });

  it("finishImmediately completes without waiting", () => {
    const completed: string[] = [];
    const { result } = renderHook(() =>
      useProgressiveAssistantResponse({
        onUpdate: () => {},
        onComplete: (_id, full) => completed.push(full),
      }),
    );

    act(() => {
      result.current.start("m1", "Short reply");
      result.current.finishImmediately();
    });

    expect(result.current.isGenerating).toBe(false);
    expect(completed).toEqual(["Short reply"]);
  });

  it("cancel prevents completion callbacks", () => {
    const completed: string[] = [];
    const { result } = renderHook(() =>
      useProgressiveAssistantResponse({
        onUpdate: () => {},
        onComplete: (_id, full) => completed.push(full),
      }),
    );

    act(() => {
      result.current.start("m1", "Some longer assistant response text");
      result.current.cancel();
      vi.runAllTimers();
    });

    expect(completed).toHaveLength(0);
    expect(result.current.isGenerating).toBe(false);
  });

  it("does not apply stale generation after a newer start", () => {
    const updates: string[] = [];
    const { result } = renderHook(() =>
      useProgressiveAssistantResponse({
        onUpdate: (_id, text) => updates.push(text),
        onComplete: () => {},
      }),
    );

    act(() => {
      result.current.start("old", "Old message text here");
      result.current.start("new", "New");
      vi.runAllTimers();
    });

    expect(updates[updates.length - 1]).toBe("New");
  });

  it("shows full text immediately when reduced motion is preferred", () => {
    const matchMedia = vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
    vi.stubGlobal("matchMedia", matchMedia);

    const completed: string[] = [];
    const { result } = renderHook(() =>
      useProgressiveAssistantResponse({
        onUpdate: () => {},
        onComplete: (_id, full) => completed.push(full),
      }),
    );

    act(() => {
      result.current.start("m1", "Complete response immediately");
    });

    expect(result.current.isGenerating).toBe(false);
    expect(completed).toEqual(["Complete response immediately"]);

    vi.unstubAllGlobals();
  });
});

describe("LoadingIndicator", () => {
  it("renders the existing Thinking dots unchanged", () => {
    const { container, getByText } = render(<LoadingIndicator />);
    expect(getByText("Thinking…")).toBeTruthy();
    expect(container.querySelectorAll(".thinking-dot")).toHaveLength(3);
    expect(container.querySelector(".construction-crane-wrap")).toBeNull();
    expect(container.querySelector(".mini-crane-indicator-wrap")).toBeNull();
  });
});

describe("ConstructionCraneTextBuilder", () => {
  it("is hidden from assistive technology", () => {
    const { container } = render(<ConstructionCraneTextBuilder messageId="m1" />);
    const el = container.querySelector(".construction-crane-wrap");
    expect(el?.getAttribute("aria-hidden")).toBe("true");
    expect(container.querySelector("svg")?.getAttribute("focusable")).toBe("false");
  });

  it("uses fixed inline dimensions", () => {
    const { container } = render(<ConstructionCraneTextBuilder messageId="m1" />);
    const svg = container.querySelector(".construction-crane-svg");
    expect(svg?.getAttribute("width")).toBe("34");
    expect(svg?.getAttribute("height")).toBe("20");
    expect(svg?.getAttribute("viewBox")).toBe("0 0 96 54");
  });

  it("renders mechanical crane layers", () => {
    const { container } = render(<ConstructionCraneTextBuilder messageId="m1" />);
    expect(container.querySelector(".construction-crane-body")).toBeTruthy();
    expect(container.querySelector(".construction-crane-rear-wheel")).toBeTruthy();
    expect(container.querySelector(".construction-crane-front-wheel")).toBeTruthy();
    expect(container.querySelector(".construction-crane-boom")).toBeTruthy();
    expect(container.querySelector(".construction-crane-piston-rod")).toBeTruthy();
    expect(container.querySelector(".construction-crane-hook-sway")).toBeTruthy();
  });

  it("defines synchronized animations in CSS", () => {
    expect(indexCss).toContain("construction-crane-wheel-spin");
    expect(indexCss).toContain("construction-crane-boom-lift");
    expect(indexCss).toContain("construction-crane-piston-extend");
    expect(indexCss).not.toContain("mini-crane");
    expect(indexCss).not.toContain("forge-pulse");
    expect(indexCss).not.toContain("response-morph");
  });
});

describe("AssistantMessageContent", () => {
  it("shows construction crane only while generating", () => {
    const { rerender, container } = render(
      <AssistantMessageContent
        text="Full backend response"
        displayedText="Hello"
        messageId="msg-1"
        isGenerating={true}
        usePlainText={true}
      />,
    );
    expect(container.querySelector(".construction-crane-wrap")).toBeTruthy();
    expect(container.textContent).toContain("Hello");

    rerender(
      <AssistantMessageContent
        text="Full backend response"
        messageId="msg-1"
        isGenerating={false}
        usePlainText={false}
      />,
    );
    expect(container.querySelector(".construction-crane-wrap")).toBeNull();
    expect(container.textContent).toContain("Full backend response");
  });

  it("does not remount the crane when displayed text updates", () => {
    const { rerender, container } = render(
      <AssistantMessageContent
        text="Full backend text preserved"
        displayedText="Hello"
        messageId="msg-stable"
        isGenerating={true}
        usePlainText={true}
      />,
    );

    const craneNode = container.querySelector(".construction-crane-wrap");
    expect(craneNode).toBeTruthy();

    rerender(
      <AssistantMessageContent
        text="Full backend text preserved"
        displayedText="Hello world"
        messageId="msg-stable"
        isGenerating={true}
        usePlainText={true}
      />,
    );

    rerender(
      <AssistantMessageContent
        text="Full backend text preserved"
        displayedText="Hello world from InfraForge"
        messageId="msg-stable"
        isGenerating={true}
        usePlainText={true}
      />,
    );

    expect(container.querySelector(".construction-crane-wrap")).toBe(craneNode);
  });

  it("places crane after progressive text in document order", () => {
    const { container } = render(
      <AssistantMessageContent
        text="Backend"
        displayedText="Building response"
        messageId="msg-1"
        isGenerating={true}
        usePlainText={true}
      />,
    );
    const progressive = container.querySelector(".progressive-response");
    const crane = container.querySelector(".construction-crane-wrap");
    expect(progressive).toBeTruthy();
    expect(crane).toBeTruthy();
    expect(
      progressive?.compareDocumentPosition(crane!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});
