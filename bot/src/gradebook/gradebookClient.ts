export type GradebookStudentLookup = {
  student: {
    userId: number;
    username: string;
    email: string;
    firstName: string;
    lastName: string;
    phoneNumber: string;
    dateOfBirth: string;
  };
  class: {
    classId: number;
    name: string;
    academicYear: string;
    gradeLevel: {
      gradeLevelId: number;
      numericLevel: number;
      name: string;
    };
  };
  homeroomTeacher: {
    userId: number;
    firstName: string;
    lastName: string;
    fullName: string;
  };
};

export async function getStudentByPhone(
  phoneNumber: string,
  apiKey: string
): Promise<GradebookStudentLookup | null> {
  const url = new URL("https://gradebook-api.baghici.works/students/by-phone");
  url.searchParams.set("phone", phoneNumber);

  const res = await fetch(url, {
    method: "GET",
    headers: {
      "x-api-key": apiKey,
    },
  });

  if (res.status === 404) return null;
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Gradebook API error ${res.status}: ${body}`);
  }

  return (await res.json()) as GradebookStudentLookup;
}

