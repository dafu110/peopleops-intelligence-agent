import { ChangeEvent } from "react";
import { CheckCircle2, FileText, KeyRound, Plus, Upload, X } from "lucide-react";

type ContextPanelProps = {
  accessPassword: string;
  isExtracting: boolean;
  jdText: string;
  onClose: () => void;
  resumeFiles: string[];
  resumeText: string;
  handleFiles: (event: ChangeEvent<HTMLInputElement>) => void;
  refreshOperationalData: (password?: string) => Promise<void>;
  setAccessPassword: (value: string) => void;
  setJdText: (value: string) => void;
  setResumeText: (value: string) => void;
};

export function ContextPanel({
  accessPassword,
  isExtracting,
  jdText,
  onClose,
  resumeFiles,
  resumeText,
  handleFiles,
  refreshOperationalData,
  setAccessPassword,
  setJdText,
  setResumeText,
}: ContextPanelProps) {
  return (
    <aside className="context-panel" id="candidate-context">
      <header className="context-heading">
        <div>
          <span>候选人匹配 · 分步准备</span>
          <strong>先补齐可复核材料</strong>
          <p>添加候选人材料与岗位说明后，再在对话区生成匹配证据。</p>
        </div>
        <button aria-label="关闭任务材料" className="context-close" data-context-close onClick={onClose} type="button">
          <X size={16} />
          <span>返回对话</span>
        </button>
      </header>

      <section className="context-group">
        <div className="context-label"><FileText size={15} /> 简历或面试记录</div>
        <label className="upload-zone">
          <Upload size={16} />
          <span>{isExtracting ? "正在解析文件..." : "上传材料"}</span>
          <input multiple type="file" accept=".pdf,.docx,.txt,.md,.markdown" onChange={handleFiles} />
        </label>
        {resumeFiles.length ? <p className="file-caption">{resumeFiles.join("、")}</p> : null}
        <textarea value={resumeText} onChange={(event) => setResumeText(event.target.value)} placeholder="粘贴候选人简历、面试记录或关键事实" rows={8} />
      </section>

      <section className="context-group">
        <div className="context-label"><Plus size={15} /> 岗位说明</div>
        <textarea value={jdText} onChange={(event) => setJdText(event.target.value)} placeholder="粘贴 JD、能力要求和岗位背景" rows={8} />
      </section>

      <div className="context-ready" role="status">
        <CheckCircle2 size={15} />
        <span>{resumeText.trim() && jdText.trim() ? "材料已就绪：可在对话区开始匹配" : "完成两项材料后即可开始匹配"}</span>
      </div>

      <section className="context-group access-group">
        <div className="context-label"><KeyRound size={15} /> 访问口令</div>
        <input
          aria-label="访问口令"
          autoComplete="current-password"
          onBlur={(event) => refreshOperationalData(event.currentTarget.value)}
          onChange={(event) => setAccessPassword(event.target.value)}
          placeholder="如已启用访问控制，请输入"
          type="password"
          value={accessPassword}
        />
      </section>
    </aside>
  );
}
