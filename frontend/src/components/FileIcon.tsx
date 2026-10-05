import {
  FilePdf,
  FilePpt,
  FileCode,
  Image,
  Waveform,
  VideoCamera,
  FileText,
} from "@phosphor-icons/react";

export function FileIcon({
  modality,
  size = 22,
}: {
  modality: string;
  size?: number;
}) {
  const Icon =
    modality === "document"
      ? FilePdf
      : modality === "presentation"
        ? FilePpt
        : modality === "code"
          ? FileCode
          : modality === "image"
            ? Image
            : modality === "audio"
              ? Waveform
              : modality === "video"
                ? VideoCamera
                : FileText;
  return <Icon size={size} weight="duotone" />;
}
