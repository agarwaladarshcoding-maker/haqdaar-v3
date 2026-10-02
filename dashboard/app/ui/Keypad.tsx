// The phone keypad, with what each key means on a Haqdaar call. Only keys whose meaning is
// fixed in the engine carry a label.
const KEYS: { k: string; says?: string; lang?: string }[] = [
  { k: "1", says: "हिंदी", lang: "hi" },
  { k: "2", says: "मराठी", lang: "mr" },
  { k: "3", says: "English" },
  { k: "4" }, { k: "5" }, { k: "6" },
  { k: "7" }, { k: "8" }, { k: "9" },
  { k: "*" },
  { k: "0", says: "don't know" },
  { k: "#", says: "say again" },
];

export default function Keypad() {
  return (
    <div className="keypad" aria-label="What the keys do on a call: 1 Hindi, 2 Marathi, 3 English, 0 don't know, hash say again">
      {KEYS.map((key) => (
        <span className={`key${key.says ? " has-says" : ""}`} key={key.k} aria-hidden="true">
          <b>{key.k}</b>
          {key.says && <i lang={key.lang}>{key.says}</i>}
        </span>
      ))}
    </div>
  );
}
