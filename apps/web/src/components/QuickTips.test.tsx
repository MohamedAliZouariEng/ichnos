import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QuickTips, TIPS, seenQuickTips } from "./QuickTips";

describe("QuickTips", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("walks through the cards and remembers that they were seen", () => {
    const onClose = vi.fn();
    render(<QuickTips onClose={onClose} />);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(`Quick tips · 1 of ${TIPS.length}`)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
    expect(seenQuickTips()).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(within(dialog).getByRole("heading", { name: TIPS[1]!.title })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(within(dialog).getByRole("heading", { name: TIPS[0]!.title })).toBeInTheDocument();

    for (let i = 0; i < TIPS.length - 1; i += 1) {
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
    }
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(onClose).toHaveBeenCalled();
    expect(seenQuickTips()).toBe(true);
  });

  it("can be skipped, and closes with Escape", () => {
    const onClose = vi.fn();
    const { unmount } = render(<QuickTips onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(seenQuickTips()).toBe(true);
    unmount();

    window.localStorage.clear();
    render(<QuickTips onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
    expect(seenQuickTips()).toBe(true);
  });

  it("survives a browser that refuses storage", () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(seenQuickTips()).toBe(false); // so the tips appear again, rather than failing
    const onClose = vi.fn();
    render(<QuickTips onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onClose).toHaveBeenCalled();
    getItem.mockRestore();
    setItem.mockRestore();
  });
});
