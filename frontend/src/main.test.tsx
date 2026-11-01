import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "./i18n";
import { Shell } from "./app/App";

function renderShell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><Shell/></MemoryRouter></QueryClientProvider>);
}

function response(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

beforeEach(async () => {
  localStorage.clear();
  await i18n.changeLanguage("vi");
  vi.stubGlobal("fetch", vi.fn((input: string | URL | Request) => {
    const path = String(input);
    if (path.includes("/auth/login")) return Promise.resolve(response({ access_token: "session-test-token", token_type: "bearer", expires_in: 3600 }));
    if (path.includes("/dashboard")) return Promise.resolve(response({ agents_total: 7, agents_enabled: 7, audit_events_last_24h: 0, monthly_budget_usd: 50, timezone: "Asia/Ho_Chi_Minh", external_execution_enabled: false }));
    if (path.includes("/budgets/current")) return Promise.resolve(response({ account: { limit_amount: "50", reserve_amount: "5", currency: "USD" }, committed_amount: "0", available_amount: "45", usage_percent: "0", warning_thresholds_reached: [], hard_stop: false }));
    if (path.includes("/approvals")) return Promise.resolve(response({ items: [] }));
    return Promise.resolve(response([]));
  }));
});

afterEach(() => cleanup());

describe("Command Center shell", () => {
  it("requires an in-memory Owner token before loading API data", () => {
    renderShell();
    expect(screen.getByRole("heading", { name: "Kết nối an toàn" })).toBeInTheDocument();
    expect(localStorage.getItem("ownerToken")).toBeNull();
  });

  it("loads only verified dashboard API responses after a token is entered", async () => {
    renderShell();
    fireEvent.change(screen.getByLabelText("Tên đăng nhập Admin"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu Admin"), { target: { value: "password" } });
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
    await waitFor(() => expect(screen.getByText("Tổng agent")).toBeInTheDocument());
    expect(screen.getAllByText("7")).toHaveLength(2);
    expect(fetch).toHaveBeenCalled();
    expect(localStorage.getItem("ownerToken")).toBeNull();
  });

  it("switches the complete shell navigation to English", async () => {
    renderShell();
    fireEvent.click(screen.getByLabelText("Chuyển ngôn ngữ"));
    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
    expect(screen.getByText("Approval Center")).toBeInTheDocument();
  });
});
