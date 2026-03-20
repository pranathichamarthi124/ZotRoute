import React, { useState } from "react";
import MapView from "./MapView";
import Navbar from "./Navbar";

function App() {
  const [filter, setFilter] = useState("all");
  const [isPanelOpen, setIsPanelOpen] = useState(true);
  return (
    <div className="App">
      <Navbar filter={filter} setFilter={setFilter} />
      <MapView
        filter={filter}
        isPanelOpen={isPanelOpen}
        setIsPanelOpen={setIsPanelOpen}
      />
    </div>
  );
}

export default App;
