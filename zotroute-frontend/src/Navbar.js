import React from "react";
import "./Navbar.css";

export default function Navbar({ filter, setFilter }) {
  return (
    <nav className="nav">
      <div className="nav-proj-name">
        <h1>ZotRoute</h1>
        <p>One-Stop UCI Commute</p>
      </div>
      <div className="filter-buttons">
        <button
          className={filter === "all" ? "active" : ""}
          onClick={() => setFilter("all")}
        >
          All Routes
        </button>
        <button
          className={filter === "AntExp" ? "active" : ""}
          onClick={() => setFilter("AntExp")}
        >
          Anteater Express
        </button>
        <button
          className={filter === "OCTA" ? "active" : ""}
          onClick={() => setFilter("OCTA")}
        >
          OCTA
        </button>
      </div>
    </nav>
  );
}
