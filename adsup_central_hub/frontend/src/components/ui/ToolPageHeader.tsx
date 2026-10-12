import type { ReactNode } from 'react';

type Props = {
  title: string;
  description: string;
  status?: ReactNode;
};

export default function ToolPageHeader({ title, description, status }: Props) {
  return (
    <header className="tool-page-header">
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {status && <div className="tool-page-header__status">{status}</div>}
    </header>
  );
}
