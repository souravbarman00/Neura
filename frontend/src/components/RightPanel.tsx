import { useState } from "react";
import type { Source } from "../types";
import { File, Doc, Shield, Lock, Close, ChevronDown } from "../icons";

interface Props {
  open: boolean;
  sources: Source[];
  kbChunks: number | null;
  network: string;
  onClose(): void;
}

export default function RightPanel({ open, sources, kbChunks, network, onClose }: Props) {
  const isNeura = network === "neura";
  const [srcOpen, setSrcOpen] = useState(true);
  return (
    <aside className={"right" + (open ? " open" : "")}>
      <div className="right-topbar">
        <span className="right-topbar-title">Details</span>
        <button className="rclose" onClick={onClose}><Close /></button>
      </div>
      <div className={"rsection" + (srcOpen ? "" : " collapsed")}>
        <button className="rhead rhead-btn" onClick={() => setSrcOpen((v) => !v)}>
          <h3>Sources in this answer</h3>
          {sources.length > 0 && <span className="badge">{sources.length}</span>}
          <span className="grow" />
          <ChevronDown className={"rchev" + (srcOpen ? "" : " up")} />
        </button>
        {srcOpen &&
          (sources.length === 0 ? (
            <div className="card">
              <div className="muted-empty">Ask something — the files Neura used will appear here.</div>
            </div>
          ) : (
            <div className="card know">
              {sources.map((s, i) => (
                <div className="k" key={i}>
                  <div className="ki"><File /></div>
                  <div>
                    <div className="kt">{s.name}</div>
                    <div className="kc">
                      {s.source}
                      {s.score ? ` · match ${s.score}` : ""}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ))}
      </div>

      {isNeura && (<>
      <div>
        <div className="rhead"><h3>What Neura knows about you</h3></div>
        <div className="card know">
          <div className="k">
            <div className="ki"><Doc /></div>
            <div>
              <div className="kt">Local knowledge base</div>
              <div className="kc">
                {kbChunks == null ? "Indexing your folders on-device" : `${kbChunks.toLocaleString()} chunks indexed on-device`}
              </div>
            </div>
          </div>
          <div className="k">
            <div className="ki"><Shield /></div>
            <div>
              <div className="kt">Embeddings stay on device</div>
              <div className="kc">all-MiniLM · nothing uploaded</div>
            </div>
          </div>
        </div>
      </div>

      <div>
        <div className="rhead">
          <h3>Private vault</h3>
          <span className="badge">sly_data</span>
        </div>
        <div className="card">
          <div className="vault">
            <div className="v"><Lock />Credentials<span className="val">••••••••</span></div>
            <div className="v"><Lock />API tokens<span className="val">••••••••</span></div>
          </div>
          <div className="mnote">
            Sensitive values ride through sly_data — used by tools on your device, never placed in a
            model prompt.
          </div>
        </div>
      </div>
      </>)}
    </aside>
  );
}
