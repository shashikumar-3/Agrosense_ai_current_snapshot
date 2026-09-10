import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LandingPage from "@/pages/LandingPage";

const authMock = vi.hoisted(() => ({ useAuth: vi.fn() }));

vi.mock("@/hooks/use-auth", () => ({ useAuth: authMock.useAuth }));

function CurrentPath() {
  return <span data-testid="current-path">{useLocation().pathname}</span>;
}

function renderLandingPage() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <LandingPage />
      <CurrentPath />
    </MemoryRouter>,
  );
}

describe("LandingPage", () => {
  beforeEach(() => {
    authMock.useAuth.mockReset();
  });

  it("sends signed-out visitors to login before detection", () => {
    authMock.useAuth.mockReturnValue({ user: null, isLoading: false });
    renderLandingPage();

    fireEvent.click(screen.getByRole("button", { name: /login to start detection/i }));

    expect(screen.getByTestId("current-path")).toHaveTextContent("/login");
  });

  it("opens detection for an authenticated visitor", () => {
    authMock.useAuth.mockReturnValue({ user: { id: "1", email: "farmer@example.com" }, isLoading: false });
    renderLandingPage();

    fireEvent.click(screen.getByRole("button", { name: /start detection/i }));

    expect(screen.getByTestId("current-path")).toHaveTextContent("/detect");
  });
});
