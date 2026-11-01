import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { Shell } from "./app/App";

const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
const root = document.getElementById("root");

if (root) createRoot(root).render(
  <React.StrictMode><QueryClientProvider client={client}><BrowserRouter><Shell/></BrowserRouter></QueryClientProvider></React.StrictMode>,
);
