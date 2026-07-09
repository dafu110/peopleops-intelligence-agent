import { BarChart3, BriefcaseBusiness, Building2, LockKeyhole, Upload, type LucideIcon } from "lucide-react";
import { ChangeEvent } from "react";

import { API_BASE } from "../lib/api";
import type { ProductView } from "../lib/ui-helpers";

type NavigationItem = {
  id: ProductView;
  label: string;
  value: string;
  icon: LucideIcon;
};

type UsageItem = {
  label: string;
  value: string | number;
};

type ContextPanelProps = {
  accessPassword: string;
  activeProductView: ProductView;
  isExtracting: boolean;
  jdText: string;
  navigationItems: NavigationItem[];
  resumeFiles: string[];
  resumeText: string;
  tenantName: string;
  usageItems: UsageItem[];
  handleFiles: (event: ChangeEvent<HTMLInputElement>) => void;
  refreshOperationalData: (password?: string) => Promise<void>;
  setAccessPassword: (value: string) => void;
  setActiveProductView: (value: ProductView) => void;
  setJdText: (value: string) => void;
  setResumeText: (value: string) => void;
};

export function ContextPanel({
  accessPassword,
  activeProductView,
  isExtracting,
  jdText,
  navigationItems,
  resumeFiles,
  resumeText,
  tenantName,
  usageItems,
  handleFiles,
  refreshOperationalData,
  setAccessPassword,
  setActiveProductView,
  setJdText,
  setResumeText,
}: ContextPanelProps) {
  return (
    <aside className="context-panel" id="candidate-context">
      <div className="brand-block">
        <div className="brand-mark">P</div>
        <div>
          <p className="eyebrow">PeopleOps</p>
          <h1>智能控制台</h1>
        </div>
      </div>

      <section className="tenant-card" aria-label="租户信息">
        <div className="tenant-mark">
          <Building2 size={17} />
        </div>
        <div>
          <span>当前租户</span>
          <strong>{tenantName}</strong>
        </div>
        <em>Demo</em>
      </section>

      <nav className="side-nav" aria-label="产品导航">
        {navigationItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              aria-current={activeProductView === item.id ? "page" : undefined}
              className={activeProductView === item.id ? "active" : ""}
              key={item.label}
              onClick={() => setActiveProductView(item.id)}
              type="button"
            >
              <Icon size={16} />
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </button>
          );
        })}
      </nav>

      <section className="panel-section">
        <div className="section-title">
          <BriefcaseBusiness size={16} />
          候选人与岗位上下文
        </div>
        <label className="file-drop">
          <Upload size={18} />
          <span>{isExtracting ? "正在解析文档" : "上传简历或材料"}</span>
          <input multiple type="file" accept=".pdf,.docx,.txt,.md,.markdown" onChange={handleFiles} />
        </label>
        <div className="file-list">
          {resumeFiles.length ? resumeFiles.map((name) => <span key={name}>{name}</span>) : "支持 PDF、DOCX、TXT、MD；上传后由后端解析文本。"}
        </div>
        <textarea
          value={resumeText}
          onChange={(event) => setResumeText(event.target.value)}
          placeholder="候选人简历、面试记录或关键摘要会出现在这里。"
          rows={5}
        />
        <textarea
          value={jdText}
          onChange={(event) => setJdText(event.target.value)}
          placeholder="粘贴岗位 JD、能力要求和年限要求。"
          rows={5}
        />
      </section>

      <section className="panel-section compact">
        <div className="section-title">
          <LockKeyhole size={16} />
          访问与后端
        </div>
        <form className="access-form" onSubmit={(event) => event.preventDefault()}>
          <input
            aria-label="访问口令"
            autoComplete="current-password"
            value={accessPassword}
            onChange={(event) => setAccessPassword(event.target.value)}
            onBlur={(event) => refreshOperationalData(event.currentTarget.value)}
            type="password"
            placeholder="访问口令"
          />
        </form>
        <p className="subtle">API: {API_BASE}</p>
      </section>

      <section className="usage-card" aria-label="本月用量">
        <div className="section-title">
          <BarChart3 size={16} />
          本月用量
        </div>
        <div className="usage-grid">
          {usageItems.map((item) => (
            <div key={item.label}>
              <strong>{item.value}</strong>
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      </section>
    </aside>
  );
}
