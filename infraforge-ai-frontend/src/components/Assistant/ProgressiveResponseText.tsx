import React, { memo, useMemo } from "react";

interface Props {
  text: string;
  isGenerating: boolean;
}

/** Split visible text so the newest word gets a brief construction highlight. */
function splitTrailingWord(text: string): { prefix: string; trailing: string } {
  if (!text) return { prefix: "", trailing: "" };
  const match = text.match(/^(.*?)(\S+)(\s*)$/s);
  if (!match) return { prefix: "", trailing: text };
  return {
    prefix: match[1],
    trailing: `${match[2]}${match[3]}`,
  };
}

function ProgressiveResponseText({ text, isGenerating }: Props) {
  const { prefix, trailing } = useMemo(
    () => splitTrailingWord(text),
    [text],
  );

  if (!isGenerating || !trailing) {
    return <>{text}</>;
  }

  return (
    <>
      {prefix}
      <span key={trailing} className="progressive-word-trail">
        {trailing}
      </span>
    </>
  );
}

export default memo(ProgressiveResponseText);
