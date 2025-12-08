-- CreateTable
CREATE TABLE "users" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "email" TEXT NOT NULL,
    "password" TEXT NOT NULL,
    "firstName" TEXT,
    "lastName" TEXT,
    "role" TEXT NOT NULL DEFAULT 'USER',
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP NOT NULL,
    "parentId" TEXT,
    CONSTRAINT "users_parentId_fkey" FOREIGN KEY ("parentId") REFERENCES "users" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "user_settings" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" TEXT NOT NULL,
    "originZip" TEXT,
    "defaultMarkup" REAL NOT NULL DEFAULT 10.0,
    "fuelSurcharge" REAL NOT NULL DEFAULT 16.0,
    "dasSurcharge" REAL NOT NULL DEFAULT 1.98,
    "edasSurcharge" REAL NOT NULL DEFAULT 3.92,
    "remoteSurcharge" REAL NOT NULL DEFAULT 14.15,
    "dimDivisor" REAL NOT NULL DEFAULT 139.0,
    "standardMarkup" REAL NOT NULL DEFAULT 0.0,
    "expeditedMarkup" REAL NOT NULL DEFAULT 10.0,
    "priorityMarkup" REAL NOT NULL DEFAULT 15.0,
    "nextDayMarkup" REAL NOT NULL DEFAULT 25.0,
    "createdAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP NOT NULL,
    CONSTRAINT "user_settings_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "analyses" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" TEXT NOT NULL,
    "fileName" TEXT NOT NULL,
    "fileSize" INTEGER NOT NULL,
    "filePath" TEXT,
    "status" TEXT NOT NULL DEFAULT 'PENDING',
    "columnMapping" TEXT,
    "amazonRate" REAL,
    "fuelSurcharge" REAL,
    "serviceLevel" TEXT,
    "markupPercent" REAL,
    "totalPackages" INTEGER,
    "totalCurrentCost" REAL,
    "totalAmazonCost" REAL,
    "totalSavings" REAL,
    "percentSavings" REAL,
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP NOT NULL,
    "completedAt" TIMESTAMP,
    CONSTRAINT "analyses_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "column_profiles" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "mapping" TEXT NOT NULL,
    "isPublic" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP NOT NULL,
    CONSTRAINT "column_profiles_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "audit_logs" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" TEXT,
    "action" TEXT NOT NULL,
    "details" TEXT,
    "ipAddress" TEXT,
    "userAgent" TEXT,
    "createdAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- CreateIndex
CREATE UNIQUE INDEX "users_email_key" ON "users"("email");

-- CreateIndex
CREATE UNIQUE INDEX "user_settings_userId_key" ON "user_settings"("userId");

-- CreateIndex
CREATE UNIQUE INDEX "column_profiles_userId_name_key" ON "column_profiles"("userId", "name");
