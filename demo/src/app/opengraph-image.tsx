import { ImageResponse } from "next/og";

export const alt = "HIP-4 MM Simulator causal replay";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const dynamic = "force-static";

export default function OpenGraphImage() {
  return new ImageResponse(
    <div
      style={{
        alignItems: "stretch",
        background: "white",
        color: "#171821",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        justifyContent: "space-between",
        padding: "72px 76px",
        width: "100%",
      }}
    >
      <div style={{ alignItems: "center", display: "flex", gap: 18 }}>
        <div style={{ display: "flex", gap: 6 }}>
          {["#b52155", "#b52155", "#d9dbe2", "#187b58"].map((color) => (
            <div
              key={color}
              style={{ background: color, borderRadius: 3, height: 32, width: 9 }}
            />
          ))}
        </div>
        <span style={{ fontSize: 28, fontWeight: 700 }}>HIP-4 MM Simulator</span>
        <span
          style={{
            border: "1px solid #d9dbe2",
            borderRadius: 18,
            color: "#616371",
            fontSize: 18,
            padding: "6px 12px",
          }}
        >
          v0.2.0 · experimental alpha
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
        <div
          style={{
            fontSize: 62,
            fontWeight: 750,
            letterSpacing: "-2px",
            lineHeight: 1.05,
            maxWidth: 940,
          }}
        >
          See exactly when a HIP-4 paper order earns a fill.
        </div>
        <div style={{ color: "#616371", fontSize: 27, maxWidth: 930 }}>
          Observed L2 → aggressor trade → queue consumption → partial fill
        </div>
      </div>
      <div
        style={{
          borderTop: "1px solid #d9dbe2",
          display: "flex",
          fontSize: 21,
          justifyContent: "space-between",
          paddingTop: 24,
        }}
      >
        <span>Deterministic replay · spot-safe accounting</span>
        <span style={{ color: "#b52155" }}>github.com/horn111/hip4-mm-simulator</span>
      </div>
    </div>,
    size,
  );
}
