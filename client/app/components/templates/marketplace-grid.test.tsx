import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketplaceGrid } from "./marketplace-grid";
import type { MarketplaceItem } from "@/lib/types";

const mockItem = (id: string, name: string, category = "general"): MarketplaceItem => ({
  template: {
    id,
    workspace_id: null,
    name,
    description: `Description for ${name}`,
    visibility: "curated",
    latest_version: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  entry: {
    id: `entry-${id}`,
    template_id: id,
    category,
    featured: false,
    ranking_weight: 1.0,
    tags: ["tag1", "tag2"],
    published_at: new Date().toISOString(),
  },
});

describe("MarketplaceGrid", () => {
  it("renders marketplace cards from items prop", () => {
    const items = [mockItem("1", "Research Bot", "research"), mockItem("2", "Code Bot", "code")];
    render(<MarketplaceGrid items={items} onInstall={vi.fn()} />);
    expect(screen.getByText("Research Bot")).toBeInTheDocument();
    expect(screen.getByText("Code Bot")).toBeInTheDocument();
  });

  it("renders category tags on cards", () => {
    const items = [mockItem("1", "Research Bot", "research")];
    render(<MarketplaceGrid items={items} onInstall={vi.fn()} />);
    expect(screen.getByText("research")).toBeInTheDocument();
  });

  it("calls onInstall with correct templateId when install button clicked", async () => {
    const user = userEvent.setup();
    const onInstall = vi.fn();
    const items = [mockItem("template-abc", "My Bot")];
    render(<MarketplaceGrid items={items} onInstall={onInstall} />);
    await user.click(screen.getByRole("button", { name: /install my bot/i }));
    expect(onInstall).toHaveBeenCalledWith("template-abc");
  });

  it("renders empty state when no items", () => {
    render(<MarketplaceGrid items={[]} onInstall={vi.fn()} />);
    expect(screen.getByText(/no templates found/i)).toBeInTheDocument();
  });

  it("renders multiple items without errors", () => {
    const items = Array.from({ length: 5 }, (_, i) => mockItem(`id-${i}`, `Bot ${i}`));
    render(<MarketplaceGrid items={items} onInstall={vi.fn()} />);
    for (let i = 0; i < 5; i++) {
      expect(screen.getByText(`Bot ${i}`)).toBeInTheDocument();
    }
  });
});
