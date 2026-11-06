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

afterEach(() => { cleanup(); localStorage.clear(); sessionStorage.clear(); vi.useRealTimers(); });

function signIn(remember = false) {
  fireEvent.change(screen.getByLabelText("Tên đăng nhập Admin"), { target: { value: "admin" } });
  fireEvent.change(screen.getByLabelText("Mật khẩu Admin"), { target: { value: "password" } });
  if (remember) fireEvent.click(screen.getByLabelText("Ghi nhớ đăng nhập"));
  // Pressing Enter in a field submits the enclosing form; the browser does this natively.
  fireEvent.submit(screen.getByLabelText("Mật khẩu Admin").closest("form")!);
}

describe("Command Center shell", () => {
  it("shows a full-screen sign-in before any API data is requested", () => {
    renderShell();
    expect(screen.getByRole("heading", { name: "Đăng nhập Owner" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Ghi nhớ đăng nhập")).not.toBeChecked();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("validates empty credentials without calling the API", () => {
    renderShell();
    fireEvent.submit(screen.getByLabelText("Mật khẩu Admin").closest("form")!);
    expect(screen.getByRole("alert")).toHaveTextContent("Nhập tên đăng nhập và mật khẩu.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("signs in on form submit and keeps an unremembered session only for this tab", async () => {
    renderShell();
    signIn();
    await waitFor(() => expect(screen.getByText("Tổng agent")).toBeInTheDocument());
    expect(screen.getAllByText("7")).toHaveLength(2);
    const login = vi.mocked(fetch).mock.calls.find(([url]) => String(url).includes("/auth/login"));
    expect(JSON.parse(String(login?.[1]?.body))).toEqual({ username: "admin", password: "password" });
    expect(localStorage.getItem("ownerSession")).toBeNull();
    expect(JSON.parse(sessionStorage.getItem("ownerSession")!)).toMatchObject({ token: "session-test-token", username: "admin" });
  });

  it("remembers the session across reloads until sign-out, then prefills the username", async () => {
    const first = renderShell();
    signIn(true);
    await waitFor(() => expect(screen.getByText("Tổng agent")).toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem("ownerSession")!)).toMatchObject({ token: "session-test-token" });
    first.unmount();
    renderShell();
    expect(await screen.findByText("Tổng agent")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Đăng xuất" }));
    expect(screen.getByRole("heading", { name: "Đăng nhập Owner" })).toBeInTheDocument();
    expect(localStorage.getItem("ownerSession")).toBeNull();
    expect(screen.getByLabelText("Tên đăng nhập Admin")).toHaveValue("admin");
    expect(screen.getByLabelText("Ghi nhớ đăng nhập")).toBeChecked();
  });

  it("discards an expired stored session", () => {
    localStorage.setItem("ownerSession", JSON.stringify({ token: "old", expiresAt: Date.now() - 1000, username: "admin" }));
    renderShell();
    expect(screen.getByRole("heading", { name: "Đăng nhập Owner" })).toBeInTheDocument();
    expect(localStorage.getItem("ownerSession")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("returns to sign-in when the backend rejects the session", async () => {
    localStorage.setItem("ownerSession", JSON.stringify({ token: "revoked", expiresAt: Date.now() + 60_000, username: "admin" }));
    vi.mocked(fetch).mockImplementation(async () => ({ ok: false, status: 401, json: async () => ({ detail: "Unauthorized" }) }) as Response);
    renderShell();
    expect(await screen.findByRole("heading", { name: "Đăng nhập Owner" })).toBeInTheDocument();
    expect(localStorage.getItem("ownerSession")).toBeNull();
  });

  it("shows an invalid-credentials error and stays on the sign-in screen", async () => {
    vi.mocked(fetch).mockImplementation(async () => ({ ok: false, status: 401, json: async () => ({ detail: "Invalid" }) }) as Response);
    renderShell();
    signIn();
    expect(await screen.findByText("Tên đăng nhập hoặc mật khẩu không hợp lệ.")).toBeInTheDocument();
    expect(sessionStorage.getItem("ownerSession")).toBeNull();
  });

  it("switches the sign-in screen and the shell navigation to English", async () => {
    renderShell();
    fireEvent.click(screen.getByLabelText("Chuyển ngôn ngữ"));
    expect(await screen.findByRole("heading", { name: "Owner sign-in" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Admin username"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("Admin password"), { target: { value: "password" } });
    fireEvent.submit(screen.getByLabelText("Admin password").closest("form")!);
    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
    expect(screen.getByText("Approval Center")).toBeInTheDocument();
  });
});
