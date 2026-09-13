import React from "react";
import Crawler from "../components/Crawler";

export default function CrawlerRoute() {
  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1 className="text-display">
            Legal Intelligence & Evidence Crawler
          </h1>
          <p className="page-desc">
            Federated court record crawler for case intelligence, gazette
            notifications, and statutory corroboration.
          </p>
        </div>
      </div>
      <Crawler />
    </div>
  );
}
