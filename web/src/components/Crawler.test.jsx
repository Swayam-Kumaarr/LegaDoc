import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import Crawler from "./Crawler";
import * as crawlerApi from "../api/crawler";

describe("Crawler Component", () => {
  it("renders heading and input form controls", () => {
    render(<Crawler />);
    expect(
      screen.getByText(/Public Legal Gazette & e-Courts Evidence Crawler/i),
    ).toBeTruthy();
    expect(
      screen.getByPlaceholderText(/State vs. Kumar, Section 420/i),
    ).toBeTruthy();
    expect(screen.getByText("Initiate Crawl")).toBeTruthy();
  });

  it("submits crawl request and renders result table with hash and status", async () => {
    vi.spyOn(crawlerApi, "startCrawlJob").mockResolvedValueOnce({
      status: "completed",
      results: [
        {
          id: "TEST-CRW-101",
          source: "e-Courts Portal",
          title: "State vs. Test Subject",
          filing_date: "2026-09-10",
          matched_section: "Section 420 IPC",
          hash: "abc1234567890defabc1234567890defabc1234567890defabc1234567890def",
          status: "Verified Ingested",
        },
      ],
    });

    render(<Crawler />);
    const input = screen.getByPlaceholderText(/State vs. Kumar, Section 420/i);
    fireEvent.change(input, { target: { value: "State vs. Test Subject" } });

    const crawlBtn = screen.getByText("Initiate Crawl");
    fireEvent.click(crawlBtn);

    await waitFor(() => {
      expect(screen.getByText("TEST-CRW-101")).toBeTruthy();
      expect(screen.getByText("State vs. Test Subject")).toBeTruthy();
      expect(screen.getByText("Section 420 IPC")).toBeTruthy();
      expect(screen.getByText("Verified Ingested")).toBeTruthy();
    });
  });

  it("displays empty state when crawl yields no records", async () => {
    vi.spyOn(crawlerApi, "startCrawlJob").mockResolvedValueOnce({
      status: "completed",
      results: [],
    });

    render(<Crawler />);
    const crawlBtn = screen.getByText("Initiate Crawl");
    fireEvent.click(crawlBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/No records or matching gazette dockets found/i),
      ).toBeTruthy();
    });
  });

  it("displays error message when crawl operation fails", async () => {
    vi.spyOn(crawlerApi, "startCrawlJob").mockRejectedValueOnce(
      new Error("Gateway timeout connecting to e-Courts node"),
    );

    render(<Crawler />);
    const crawlBtn = screen.getByText("Initiate Crawl");
    fireEvent.click(crawlBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/Gateway timeout connecting to e-Courts node/i),
      ).toBeTruthy();
    });
  });
});
