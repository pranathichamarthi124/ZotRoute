import React from "react";
import "./Navbar.css";

function Navbar({ filter, setFilter }) {
  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <h1>🚍 ZotRoute</h1>
        <p>UCI Transit Guide</p>
      </div>

      <div className="filter-buttons">
        <button
          className={filter === "all" ? "active" : ""}
          onClick={() => setFilter("all")}
        >
          All Routes
        </button>
        <button
          className={filter === "AE" ? "active" : ""}
          onClick={() => setFilter("AE")}
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

export default Navbar;
