import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockApi } from "../test/http";
import { SessionControl } from "./SessionControl";

const SIGNED_OUT = { approvals_enabled: true, signed_in: false, approver: null, expires_at: null };
const SIGNED_IN = {
  approvals_enabled: true,
  signed_in: true,
  approver: "human:MohamedAliZouariEng",
  expires_at: "2026-09-20T06:00:00Z",
};

describe("SessionControl", () => {
  it("signs in and shows the approver", async () => {
    mockApi({
      "GET /api/session": () => jsonResponse(200, SIGNED_OUT),
      "POST /api/session": () => jsonResponse(200, SIGNED_IN),
    });
    render(<SessionControl />);
    fireEvent.click(await screen.findByRole("button", { name: "Sign in to approve" }));
    fireEvent.change(screen.getByLabelText("Approver passphrase"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("human:MohamedAliZouariEng")).toBeInTheDocument();
  });

  it("explains a wrong passphrase", async () => {
    mockApi({
      "GET /api/session": () => jsonResponse(200, SIGNED_OUT),
      "POST /api/session": () => jsonResponse(401, { detail: "Wrong passphrase." }),
    });
    render(<SessionControl />);
    fireEvent.click(await screen.findByRole("button", { name: "Sign in to approve" }));
    fireEvent.change(screen.getByLabelText("Approver passphrase"), { target: { value: "nope" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong passphrase.");
  });

  it("says when approvals are disabled", async () => {
    mockApi({
      "GET /api/session": () => jsonResponse(200, { ...SIGNED_OUT, approvals_enabled: false }),
    });
    render(<SessionControl />);
    expect(await screen.findByText("Approvals disabled")).toBeInTheDocument();
  });
});
