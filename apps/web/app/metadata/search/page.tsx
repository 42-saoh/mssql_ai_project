import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function MetadataSearchRedirectPage() {
  redirect("/metadata/design?intent=search");
}
